import io
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from groq import Groq, APIConnectionError, AuthenticationError, RateLimitError, APIError
from config import GROQ_API_KEY, GROQ_STT_MODEL, GROQ_LLM_MODEL, GROQ_LANGUAGE

logger = logging.getLogger("GroqClient")

SYSTEM_PROMPT = """Você é o processador de comandos de um aplicativo de tarefas. 
Analise a transcrição de voz do usuário e o estado atual das tarefas. Retorne APENAS um JSON válido no seguinte formato:

{
  "action": "add" | "toggle_complete" | "delete" | "clear_completed" | "none",
  "task_id": "string com o id caso a ação seja toggle ou delete, senão null",
  "task_title": "título normalizado da tarefa (sem comandos de voz redundantes)",
  "priority": "baixa" | "media" | "alta",
  "category": "Trabalho" | "Pessoal" | "Estudos" | "Geral",
  "due_time": "horário no formato HH:MM (ex: 15:30) caso mencionado, senão null",
  "feedback_message": "frase curta (máx 5 palavras) confirmando a ação"
}

Diretrizes para 'category':
- "Trabalho": reuniões, clientes, relatórios, projetos profissionais, GEL, escritório, etc.
- "Pessoal": compras, casa, remédio, treino, academia, família, contas pessoais, médico, etc.
- "Estudos": cursos, aulas, provas, livros, faculdade, etc.
- "Geral": tarefas genéricas que não pertençam exclusivamente às anteriores.
"""

class GroqClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = (api_key or GROQ_API_KEY).strip()
        self._client: Optional[Groq] = None
        if self.api_key:
            self._init_client()

    def _init_client(self):
        try:
            self._client = Groq(api_key=self.api_key)
        except Exception as e:
            logger.error(f"Erro ao instanciar Groq SDK: {e}")
            self._client = None

    def set_api_key(self, key: str):
        """Atualiza a chave de API em tempo de execução."""
        self.api_key = key.strip()
        if self.api_key:
            self._init_client()
        else:
            self._client = None

    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 10)

    def transcribe_audio(self, wav_bytes: bytes) -> str:
        """
        Envia o áudio em memória para o endpoint /audio/transcriptions da Groq
        usando whisper-large-v3 com language='pt'.
        """
        if not self.is_configured():
            raise ValueError("Chave de API da Groq não configurada. Defina GROQ_API_KEY no arquivo .env.")

        if not wav_bytes or len(wav_bytes) < 100:
            raise ValueError("Áudio gravado está vazio ou inaudível.")

        # Groq client espera uma tupla (nome_arquivo, bytes) ou buffer
        file_tuple = ("speech.wav", wav_bytes)

        try:
            transcription = self._client.audio.transcriptions.create(
                file=file_tuple,
                model=GROQ_STT_MODEL,
                language=GROQ_LANGUAGE,
                response_format="json",
                temperature=0.0
            )
            text = (transcription.text or "").strip()
            if not text:
                raise ValueError("Nenhum áudio inteligível detectado.")
            return text
        except AuthenticationError:
            raise PermissionError("Chave de API da Groq inválida ou expirada.")
        except APIConnectionError:
            raise ConnectionError("Falha de conexão com a Groq Cloud. Verifique sua internet.")
        except RateLimitError:
            raise RuntimeError("Limite de requisições da Groq atingido. Aguarde alguns instantes.")
        except APIError as e:
            raise RuntimeError(f"Erro na API Groq (STT): {e.message}")
        except Exception as e:
            if isinstance(e, (ValueError, PermissionError, ConnectionError, RuntimeError)):
                raise e
            raise RuntimeError(f"Erro inesperado na transcrição: {str(e)}")

    def process_command(self, transcription: str, current_tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Envia a transcrição e o contexto de tarefas para o llama-3.3-70b-versatile
        com response_format={"type": "json_object"}.
        """
        if not self.is_configured():
            raise ValueError("Chave de API da Groq não configurada.")

        clean_text = (transcription or "").strip()
        if not clean_text:
            return {
                "action": "none",
                "task_id": None,
                "task_title": "",
                "priority": "media",
                "due_time": None,
                "feedback_message": "Nenhum comando detectado"
            }

        # Formata o estado atual para o contexto da IA
        tasks_context = [
            {
                "id": t.get("id"),
                "title": t.get("title"),
                "completed": t.get("completed", False),
                "priority": t.get("priority", "media"),
                "due_time": t.get("due_time")
            }
            for t in current_tasks
        ]

        user_content = json.dumps({
            "voice_input": clean_text,
            "current_tasks": tasks_context
        }, ensure_ascii=False)

        models_to_try = [GROQ_LLM_MODEL, "qwen/qwen3.8-27b", "openai/gpt-oss-120b"]
        last_error = None
        raw_json = None

        for model_name in models_to_try:
            try:
                response = self._client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_content}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1
                )
                raw_json = response.choices[0].message.content
                if raw_json:
                    break
            except Exception as e:
                last_error = e
                # Se for 404 (model not found), tenta o próximo modelo disponível
                if "model_not_found" in str(e) or "404" in str(e):
                    logger.info(f"Modelo {model_name} indisponível na conta, tentando alternativa...")
                    continue
                raise e

        if not raw_json:
            if last_error:
                raise last_error
            raise RuntimeError("Não foi possível obter resposta de nenhum modelo da Groq.")

        try:
            parsed = json.loads(raw_json)

            # Normalização e validação defensiva dos campos retornados
            action = parsed.get("action", "none")
            if action not in {"add", "toggle_complete", "delete", "clear_completed", "none"}:
                action = "none"

            priority = parsed.get("priority", "media")
            if priority not in {"baixa", "media", "alta"}:
                priority = "media"

            raw_cat = str(parsed.get("category") or "Geral").strip().capitalize()
            category = raw_cat if raw_cat in {"Trabalho", "Pessoal", "Estudos", "Geral"} else "Geral"

            return {
                "action": action,
                "task_id": parsed.get("task_id"),
                "task_title": parsed.get("task_title") or clean_text,
                "priority": priority,
                "category": category,
                "due_time": parsed.get("due_time"),
                "feedback_message": parsed.get("feedback_message") or "Comando processado"
            }
        except AuthenticationError:
            raise PermissionError("Chave de API da Groq inválida.")
        except APIConnectionError:
            raise ConnectionError("Falha de conexão com a Groq Cloud.")
        except RateLimitError:
            raise RuntimeError("Limite de requisições excedido.")
        except json.JSONDecodeError:
            raise ValueError("Resposta do modelo não pôde ser convertida em JSON.")
        except Exception as e:
            if isinstance(e, (ValueError, PermissionError, ConnectionError, RuntimeError)):
                raise e
            raise RuntimeError(f"Erro ao interpretar intenção: {str(e)}")

    def process_voice_command(self, wav_bytes: bytes, current_tasks: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], str]:
        """Pipeline completo: Áudio -> Whisper -> Llama 3.3 -> Ação estruturada."""
        transcription = self.transcribe_audio(wav_bytes)
        result = self.process_command(transcription, current_tasks)
        return result, transcription
