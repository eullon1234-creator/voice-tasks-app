import json
import os
import threading
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
import requests

from config import (
    BASE_DIR, GROQ_API_KEY, GROQ_LLM_MODEL,
    FIREBASE_PROJECT_ID, FIREBASE_API_KEY, FIREBASE_COLLECTION
)

logger = logging.getLogger("AIMemoryEngine")

MEMORY_FILE = BASE_DIR / "ai_memory.json"
CHAT_HISTORY_FILE = BASE_DIR / "chat_history.json"
FIRESTORE_PROFILE_COLLECTION = "ai_profile"
FIRESTORE_PROFILE_DOC = "eullon_memory"

DEFAULT_PROFILE = {
    "user_name": "Eullon",
    "about": "Profissional na GEL focado em gestão, relatórios e alta produtividade.",
    "preferences": [
        "Prefere tarefas claras e objetivas",
        "Gosta de acompanhar o tempo de foco no cronômetro",
        "Valoriza consistência e manter o streak diário"
    ],
    "work_context": [
        "Trabalha na empresa GEL com medições e relatórios técnicos"
    ],
    "personal_habits": [
        "Costuma organizar as prioridades e focar no trabalho"
    ],
    "goals": [
        "Bater a meta diária de foco de 60 minutos",
        "Manter rotina produtiva e organizada"
    ],
    "insights": [
        "A IA está aprendendo seus horários e preferências dia a dia."
    ],
    "last_updated": datetime.now().isoformat()
}

class AIMemoryEngine:
    """
    Motor de Memória Cognitiva & Copiloto Inteligente.
    Mantém o perfil evolutivo do usuário sincronizado na nuvem (Firestore) e em cache local.
    """
    def __init__(self, groq_client=None, memory_file=None):
        self.groq_client = groq_client
        self._lock = threading.Lock()
        self.memory_file = Path(memory_file) if memory_file else MEMORY_FILE
        self.memory = dict(DEFAULT_PROFILE)
        self.chat_history: List[Dict[str, str]] = []
        
        self.project_id = FIREBASE_PROJECT_ID
        self.api_key = FIREBASE_API_KEY
        
        self._load_local_memory()
        self._load_local_history()
        
        # Sincroniza memória da nuvem em background
        threading.Thread(target=self._sync_from_cloud, daemon=True).start()

    # ==================== Persistência Local ====================
    def _load_local_memory(self):
        if self.memory_file.exists():
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        self.memory = {**DEFAULT_PROFILE, **loaded}
            except Exception as e:
                logger.warning(f"Erro ao carregar memory file local: {e}")

    def _save_local_memory(self):
        try:
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.memory, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Erro ao salvar memory file local: {e}")

    def _load_local_history(self):
        if CHAT_HISTORY_FILE.exists():
            try:
                with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, list):
                        self.chat_history = loaded[-30:]  # Mantém últimas 30 mensagens
            except Exception as e:
                logger.warning(f"Erro ao carregar chat_history.json: {e}")

    def _save_local_history(self):
        try:
            with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.chat_history[-30:], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Erro ao salvar chat_history.json: {e}")

    # ==================== Sincronização Nuvem (Firestore REST) ====================
    def _sync_from_cloud(self):
        if not (self.project_id and self.api_key):
            return
        try:
            url = f"https://firestore.googleapis.com/v1/projects/{self.project_id}/databases/(default)/documents/{FIRESTORE_PROFILE_COLLECTION}/{FIRESTORE_PROFILE_DOC}?key={self.api_key}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                doc = resp.json()
                fields = doc.get("fields", {})
                cloud_data = self._firestore_to_dict(fields)
                if cloud_data:
                    with self._lock:
                        self.memory = {**self.memory, **cloud_data}
                        self._save_local_memory()
                    logger.info("🧠 Memória da IA sincronizada com sucesso do Firebase Firestore!")
            elif resp.status_code == 404:
                self._save_cloud_memory()
        except Exception as e:
            logger.warning(f"Falha na sincronização de memória da IA com Firestore: {e}")

    def _save_cloud_memory(self):
        if not (self.project_id and self.api_key):
            return
        try:
            url = f"https://firestore.googleapis.com/v1/projects/{self.project_id}/databases/(default)/documents/{FIRESTORE_PROFILE_COLLECTION}/{FIRESTORE_PROFILE_DOC}?key={self.api_key}"
            body = {"fields": self._dict_to_firestore(self.memory)}
            requests.patch(url, json=body, timeout=5)
        except Exception as e:
            logger.error(f"Erro ao enviar memória da IA para Firestore: {e}")

    def _firestore_to_dict(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        result = {}
        for k, v in fields.items():
            if "stringValue" in v:
                result[k] = v["stringValue"]
            elif "arrayValue" in v:
                items = []
                for val in v["arrayValue"].get("values", []):
                    if "stringValue" in val:
                        items.append(val["stringValue"])
                result[k] = items
        return result

    def _dict_to_firestore(self, data: Dict[str, Any]) -> Dict[str, Any]:
        fields = {}
        for k, v in data.items():
            if isinstance(v, str):
                fields[k] = {"stringValue": v}
            elif isinstance(v, list):
                fields[k] = {
                    "arrayValue": {
                        "values": [{"stringValue": str(item)} for item in v]
                    }
                }
        return fields

    # ==================== Métodos Públicos de Acesso à Memória ====================
    def get_memory(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self.memory)

    def get_chat_history(self) -> List[Dict[str, str]]:
        with self._lock:
            return list(self.chat_history)

    def add_fact_manually(self, category: str, fact: str):
        clean_fact = (fact or "").strip()
        if not clean_fact:
            return
        with self._lock:
            cat_key = category if category in self.memory and isinstance(self.memory[category], list) else "preferences"
            if clean_fact not in self.memory[cat_key]:
                self.memory[cat_key].append(clean_fact)
                self.memory["last_updated"] = datetime.now().isoformat()
                self._save_local_memory()
        threading.Thread(target=self._save_cloud_memory, daemon=True).start()

    def remove_fact(self, category: str, index: int) -> bool:
        with self._lock:
            if category in self.memory and isinstance(self.memory[category], list):
                if 0 <= index < len(self.memory[category]):
                    self.memory[category].pop(index)
                    self.memory["last_updated"] = datetime.now().isoformat()
                    self._save_local_memory()
                    threading.Thread(target=self._save_cloud_memory, daemon=True).start()
                    return True
        return False

    # ==================== Motor de Auto-Aprendizado (Extração em Background) ====================
    def trigger_background_learning(self, user_msg: str, ai_reply: str):
        threading.Thread(
            target=self._extract_facts_worker,
            args=(user_msg, ai_reply),
            daemon=True
        ).start()

    def _extract_facts_worker(self, user_msg: str, ai_reply: str):
        if not self.groq_client or not self.groq_client.is_configured():
            return

        extraction_prompt = f"""Você é o módulo de memória de longo prazo de um assistente de IA pessoal.
O usuário se chama Eullon. Analise a mensagem recente do usuário e identifique fatos duradouros, preferências, rotinas, gostos ou contexto de trabalho que valham a pena lembrar no futuro.

Mensagem do Usuário: "{user_msg}"
Resposta do Assistente: "{ai_reply}"

Memória Atual:
{json.dumps(self.get_memory(), ensure_ascii=False, indent=2)}

Retorne APENAS um JSON no seguinte formato (se nada novo foi aprendido, retorne listas vazias):
{{
  "new_preferences": ["fato novo sobre gostos ou estilo de trabalho"],
  "new_work_context": ["fato novo sobre trabalho, GEL, projetos"],
  "new_personal_habits": ["fato novo sobre rotinas ou hábitos"],
  "new_goals": ["meta ou objetivo mencionado"]
}}"""

        try:
            client = self.groq_client._client
            resp = client.chat.completions.create(
                model=GROQ_LLM_MODEL,
                messages=[
                    {"role": "system", "content": "Você é um extrator de memória conciso. Responda apenas com JSON válido."},
                    {"role": "user", "content": extraction_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            parsed = json.loads(resp.choices[0].message.content)
            
            has_updates = False
            with self._lock:
                for key, target_field in [
                    ("new_preferences", "preferences"),
                    ("new_work_context", "work_context"),
                    ("new_personal_habits", "personal_habits"),
                    ("new_goals", "goals")
                ]:
                    new_items = parsed.get(key, [])
                    if isinstance(new_items, list):
                        for item in new_items:
                            clean_item = str(item).strip()
                            if clean_item and clean_item not in self.memory[target_field]:
                                self.memory[target_field].append(clean_item)
                                has_updates = True
                
                if has_updates:
                    self.memory["last_updated"] = datetime.now().isoformat()
                    self._save_local_memory()
                    logger.info("🧠 Memória da IA evoluiu com novos fatos aprendidos sobre o Eullon!")

            if has_updates:
                self._save_cloud_memory()
        except Exception as e:
            logger.debug(f"Processamento de aprendizado em background: {e}")

    # ==================== Geração de Resposta do Copiloto ====================
    def chat_with_copilot(
        self,
        user_message: str,
        current_tasks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if not self.groq_client or not self.groq_client.is_configured():
            return {
                "reply": "Por favor, configure sua chave da Groq API para conversar com o Copiloto.",
                "suggested_task": None
            }

        clean_msg = (user_message or "").strip()
        if not clean_msg:
            return {"reply": "Como posso te ajudar hoje, Eullon?", "suggested_task": None}

        with self._lock:
            self.chat_history.append({"role": "user", "content": clean_msg, "timestamp": datetime.now().isoformat()})
            self._save_local_history()

        memory_ctx = self.get_memory()
        tasks_summary = [
            f"- [{ 'X' if t.get('completed') else ' ' }] {t.get('title')} ({t.get('category', 'Geral')} | {t.get('priority', 'media')}{' | ' + t['due_time'] if t.get('due_time') else ''})"
            for t in current_tasks[:15]
        ]

        system_instruction = f"""Você é o Copiloto Pessoal de Produtividade e Parceiro Diário do Eullon.
Você é extremamente inteligente, empático, motivador e focado em ajudá-lo a vencer o dia com leveza e alta performance.

O que você já aprendeu e sabe sobre o Eullon (Sua Memória Viva):
- Perfil: {memory_ctx.get('about')}
- Contexto de Trabalho: {', '.join(memory_ctx.get('work_context', []))}
- Gostos e Preferências: {', '.join(memory_ctx.get('preferences', []))}
- Hábitos e Rotina: {', '.join(memory_ctx.get('personal_habits', []))}
- Metas: {', '.join(memory_ctx.get('goals', []))}

Tarefas atuais do Eullon:
{chr(10).join(tasks_summary) if tasks_summary else 'Nenhuma tarefa cadastrada no momento.'}

Diretrizes de Resposta:
1. Responda diretamente ao Eullon pelo nome, com tom profissional, acolhedor e focado em produtividade.
2. Mostre que você o conhece usando detalhes do contexto dele (GEL, metas, rotina) de forma natural, sem parecer robótico.
3. Se você identificar uma tarefa ou algo prático que ele mencionou ou que faria sentido ele fazer hoje, inclua no final da resposta exatamente esta tag de ação:
   [CRIAR_TAREFA: Titulo da Tarefa | Prioridade (alta/media/baixa) | Categoria (Trabalho/Pessoal/Estudos/Geral) | Horario opcional HH:MM ou vazio]
   Exemplo: [CRIAR_TAREFA: Revisar relatório de medição da obra | alta | Trabalho | 16:00]
4. Seja conciso (máximo 2 a 3 parágrafos curtos)."""

        messages = [{"role": "system", "content": system_instruction}]
        
        with self._lock:
            for h in self.chat_history[-8:-1]:
                messages.append({"role": h["role"], "content": h["content"]})
        
        messages.append({"role": "user", "content": clean_msg})

        try:
            client = self.groq_client._client
            models_to_try = [GROQ_LLM_MODEL, "qwen/qwen3.8-27b", "openai/gpt-oss-120b"]
            resp = None
            for m in models_to_try:
                try:
                    resp = client.chat.completions.create(
                        model=m,
                        messages=messages,
                        temperature=0.7,
                        max_tokens=500
                    )
                    break
                except Exception:
                    continue

            if not resp:
                raise RuntimeError("Falha ao comunicar com a IA.")

            raw_reply = resp.choices[0].message.content.strip()

            suggested_task = None
            if "[CRIAR_TAREFA:" in raw_reply:
                start = raw_reply.find("[CRIAR_TAREFA:")
                end = raw_reply.find("]", start)
                if end != -1:
                    tag_content = raw_reply[start + len("[CRIAR_TAREFA:"):end].strip()
                    parts = [p.strip() for p in tag_content.split("|")]
                    if len(parts) >= 1 and parts[0]:
                        suggested_task = {
                            "title": parts[0],
                            "priority": parts[1].lower() if len(parts) > 1 and parts[1].lower() in {"baixa", "media", "alta"} else "media",
                            "category": parts[2].capitalize() if len(parts) > 2 and parts[2].capitalize() in {"Trabalho", "Pessoal", "Estudos", "Geral"} else "Geral",
                            "due_time": parts[3] if len(parts) > 3 and parts[3] else None
                        }
                    raw_reply = (raw_reply[:start] + raw_reply[end + 1:]).strip()

            with self._lock:
                self.chat_history.append({"role": "assistant", "content": raw_reply, "timestamp": datetime.now().isoformat()})
                self._save_local_history()

            self.trigger_background_learning(clean_msg, raw_reply)

            return {
                "reply": raw_reply,
                "suggested_task": suggested_task
            }
        except Exception as e:
            logger.error(f"Erro no chat com o Copiloto: {e}")
            return {
                "reply": f"Ops, tive uma falha rápida de conexão: {str(e)}",
                "suggested_task": None
            }

    # ==================== Sugestão Diária Ativa ====================
    def generate_daily_mission(self, current_tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not self.groq_client or not self.groq_client.is_configured():
            return {
                "tip": "Defina sua principal prioridade do dia e inicie o cronômetro para manter o foco!",
                "task": None
            }

        mem = self.get_memory()
        now = datetime.now()
        dia_semana = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"][now.weekday()]

        prompt = f"""Você é o Copiloto Pessoal de IA do Eullon. Hoje é {dia_semana}, {now.strftime('%d/%m/%Y')}.
Com base no que você sabe sobre a rotina dele na GEL, seus objetivos e as tarefas existentes:
Memória:
- Trabalho: {', '.join(mem.get('work_context', []))}
- Metas: {', '.join(mem.get('goals', []))}
- Hábitos: {', '.join(mem.get('personal_habits', []))}

Tarefas atuais: {len(current_tasks)} tarefas.

Gere uma reflexão motivadora de 1 frase e sugira UMA tarefa ideal para o Eullon realizar hoje.
Retorne APENAS um JSON no formato:
{{
  "tip": "Frase curta e motivadora personalizada para hoje",
  "task_title": "Título de uma tarefa recomendada para hoje",
  "priority": "alta" | "media",
  "category": "Trabalho" | "Pessoal" | "Estudos",
  "due_time": "10:00" ou outro horário sugerido
}}"""

        try:
            client = self.groq_client._client
            resp = client.chat.completions.create(
                model=GROQ_LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.4
            )
            data = json.loads(resp.choices[0].message.content)
            return {
                "tip": data.get("tip", "Mantenha o foco nas suas principais metas de hoje!"),
                "task": {
                    "title": data.get("task_title", "Planejar tarefas do dia"),
                    "priority": data.get("priority", "alta"),
                    "category": data.get("category", "Trabalho"),
                    "due_time": data.get("due_time", "10:00")
                } if data.get("task_title") else None
            }
        except Exception:
            return {
                "tip": f"Tenha uma excelente {dia_semana}, Eullon! Comece pela sua tarefa de maior impacto.",
                "task": None
            }
