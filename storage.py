import json
import os
import threading
import logging
import requests
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path

from config import (
    DATA_FILE, FIREBASE_CREDENTIALS_PATH, FIREBASE_COLLECTION,
    FIREBASE_PROJECT_ID, FIREBASE_API_KEY
)

logger = logging.getLogger("TaskStorage")

def format_duration(seconds: int) -> str:
    """Formata segundos em texto legível como '45s', '14m 20s' ou '1h 30m'."""
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    rem_seconds = seconds % 60
    if minutes < 60:
        return f"{minutes}m {rem_seconds:02d}s"
    hours = minutes // 60
    rem_minutes = minutes % 60
    return f"{hours}h {rem_minutes:02d}m"

def format_stopwatch(seconds: int) -> str:
    """Formata segundos no formato MM:SS ou HH:MM:SS para o cronômetro."""
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

class TaskStorage:
    def __init__(self, filepath=DATA_FILE):
        self.filepath = filepath
        self.tasks: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        
        # Modo de conexão Firebase: 'admin', 'rest' ou 'local'
        self.firebase_mode = "local"
        self._db = None
        self._collection_name = FIREBASE_COLLECTION
        self.project_id = FIREBASE_PROJECT_ID
        self.api_key = FIREBASE_API_KEY
        
        self._init_firebase()
        self._load_local()

        # Sincroniza da nuvem em background se o Firebase estiver habilitado
        if self.is_firebase_connected():
            threading.Thread(target=self._sync_from_cloud, daemon=True).start()

    def _init_firebase(self):
        """Inicializa Firebase Admin SDK se houver arquivo de credenciais, ou fallback para Firestore REST."""
        cred_path = Path(FIREBASE_CREDENTIALS_PATH)
        if cred_path.is_file():
            try:
                import firebase_admin
                from firebase_admin import credentials, firestore

                if not firebase_admin._apps:
                    cred = credentials.Certificate(str(cred_path))
                    firebase_admin.initialize_app(cred)
                
                self._db = firestore.client()
                self.firebase_mode = "admin"
                logger.info("🔥 Conectado ao Firebase Firestore via Admin SDK!")
                return
            except Exception as e:
                logger.warning(f"Falha ao iniciar Firebase Admin SDK: {e}")

        # Se não tiver service account, verifica se há Project ID configurado para Firestore REST
        if self.project_id and self.api_key:
            self.firebase_mode = "rest"
            logger.info(f"🔥 Modo Firebase Firestore REST ativo para o projeto: {self.project_id}")
        else:
            self.firebase_mode = "local"
            logger.info("💾 Operando em modo armazenamento local.")

    def is_firebase_connected(self) -> bool:
        return self.firebase_mode in ("admin", "rest")

    def _load_local(self) -> None:
        """Carrega tarefas do arquivo JSON local."""
        if not os.path.exists(self.filepath):
            self.tasks = []
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    self.tasks = data
                else:
                    self.tasks = []
        except Exception as e:
            logger.error(f"Erro ao carregar tarefas locais: {e}")
            self.tasks = []

    def _save_local(self) -> None:
        """Salva tarefas no arquivo JSON local com escrita atômica segura."""
        try:
            temp_path = f"{self.filepath}.tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.tasks, f, ensure_ascii=False, indent=2)
            
            if os.path.exists(self.filepath):
                os.replace(temp_path, self.filepath)
            else:
                os.rename(temp_path, self.filepath)
        except Exception as e:
            logger.error(f"Erro ao salvar tarefas locais: {e}")

    # ==================== Helpers Firestore REST ====================
    def _dict_to_firestore_fields(self, d: Dict[str, Any]) -> Dict[str, Any]:
        fields = {}
        for k, v in d.items():
            if isinstance(v, bool):
                fields[k] = {"booleanValue": v}
            elif isinstance(v, int):
                fields[k] = {"integerValue": str(v)}
            elif isinstance(v, str):
                fields[k] = {"stringValue": v}
            elif v is None:
                fields[k] = {"nullValue": None}
            else:
                fields[k] = {"stringValue": str(v)}
        return {"fields": fields}

    def _firestore_fields_to_dict(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        fields = doc.get("fields", {})
        result = {}
        for k, v in fields.items():
            if "stringValue" in v:
                result[k] = v["stringValue"]
            elif "booleanValue" in v:
                result[k] = v["booleanValue"]
            elif "integerValue" in v:
                result[k] = int(v["integerValue"])
            elif "nullValue" in v:
                result[k] = None
            else:
                result[k] = list(v.values())[0] if v else None
        doc_name = doc.get("name", "")
        if doc_name and "id" not in result:
            result["id"] = doc_name.split("/")[-1]
        return result

    # ==================== Sincronização em Nuvem ====================
    def _sync_from_cloud(self):
        """Puxa tarefas do Firestore (Admin SDK ou REST) e sincroniza localmente."""
        if not self.is_firebase_connected():
            return

        cloud_tasks = []
        try:
            if self.firebase_mode == "admin" and self._db:
                docs = self._db.collection(self._collection_name).stream()
                for doc in docs:
                    data = doc.to_dict()
                    data["id"] = doc.id
                    cloud_tasks.append(data)
            elif self.firebase_mode == "rest":
                url = f"https://firestore.googleapis.com/v1/projects/{self.project_id}/databases/(default)/documents/{self._collection_name}?key={self.api_key}"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    raw_docs = resp.json().get("documents", [])
                    for rd in raw_docs:
                        cloud_tasks.append(self._firestore_fields_to_dict(rd))
                elif resp.status_code == 403:
                    logger.warning("Firebase Firestore retornou 403. Verifique as regras de segurança no Firebase Console.")

            if cloud_tasks:
                with self._lock:
                    cloud_ids = {t["id"] for t in cloud_tasks}
                    remaining_local = [t for t in self.tasks if t["id"] not in cloud_ids]
                    self.tasks = cloud_tasks + remaining_local
                    self._save_local()
                logger.info(f"Sincronizadas {len(cloud_tasks)} tarefas do Firebase.")
        except Exception as e:
            logger.error(f"Erro na sincronização com Firebase: {e}")

    def _async_cloud_op(self, func, *args):
        """Dispara operação de nuvem em thread de background."""
        if not self.is_firebase_connected():
            return
        threading.Thread(target=func, args=args, daemon=True).start()

    def _cloud_set_task(self, task: Dict[str, Any]):
        try:
            if self.firebase_mode == "admin" and self._db:
                self._db.collection(self._collection_name).document(task["id"]).set(task)
            elif self.firebase_mode == "rest":
                task_id = task["id"]
                url = f"https://firestore.googleapis.com/v1/projects/{self.project_id}/databases/(default)/documents/{self._collection_name}/{task_id}?key={self.api_key}"
                body = self._dict_to_firestore_fields(task)
                requests.patch(url, json=body, timeout=5)
        except Exception as e:
            logger.error(f"Erro ao salvar tarefa no Firebase ({task.get('id')}): {e}")

    def _cloud_update_task(self, task_id: str, updates: Dict[str, Any]):
        try:
            if self.firebase_mode == "admin" and self._db:
                self._db.collection(self._collection_name).document(task_id).update(updates)
            elif self.firebase_mode == "rest":
                # Busca a tarefa existente na memória e salva completa
                with self._lock:
                    task = next((t for t in self.tasks if t["id"] == task_id), None)
                if task:
                    self._cloud_set_task(task)
        except Exception as e:
            logger.error(f"Erro ao atualizar tarefa no Firebase ({task_id}): {e}")

    def _cloud_delete_task(self, task_id: str):
        try:
            if self.firebase_mode == "admin" and self._db:
                self._db.collection(self._collection_name).document(task_id).delete()
            elif self.firebase_mode == "rest":
                url = f"https://firestore.googleapis.com/v1/projects/{self.project_id}/databases/(default)/documents/{self._collection_name}/{task_id}?key={self.api_key}"
                requests.delete(url, timeout=5)
        except Exception as e:
            logger.error(f"Erro ao excluir tarefa no Firebase ({task_id}): {e}")

    def _cloud_batch_delete(self, task_ids: List[str]):
        try:
            if self.firebase_mode == "admin" and self._db:
                batch = self._db.batch()
                for tid in task_ids:
                    ref = self._db.collection(self._collection_name).document(tid)
                    batch.delete(ref)
                batch.commit()
            elif self.firebase_mode == "rest":
                for tid in task_ids:
                    self._cloud_delete_task(tid)
        except Exception as e:
            logger.error(f"Erro ao limpar tarefas no Firebase: {e}")

    # ==================== Métodos CRUD Públicos ====================
    def _generate_id(self) -> str:
        with self._lock:
            existing_ids = {t.get("id") for t in self.tasks}
            count = 1
            while f"t{count}" in existing_ids:
                count += 1
            return f"t{count}"

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.tasks)

    def get_pending_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [t for t in self.tasks if not t.get("completed", False)]

    def get_completed_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [t for t in self.tasks if t.get("completed", False)]

    def add_task(self, title: str, priority: str = "media", due_time: Optional[str] = None) -> Dict[str, Any]:
        clean_title = (title or "").strip()
        if not clean_title:
            raise ValueError("Título da tarefa não pode ser vazio")

        valid_priorities = {"baixa", "media", "alta"}
        norm_priority = priority.lower().strip() if priority else "media"
        if norm_priority not in valid_priorities:
            norm_priority = "media"

        new_task = {
            "id": self._generate_id(),
            "title": clean_title,
            "completed": False,
            "priority": norm_priority,
            "due_time": due_time.strip() if due_time else None,
            "created_at": datetime.now().isoformat(),
            "timer_running": False,
            "timer_started_at": None,
            "elapsed_seconds": 0,
            "completed_duration": None
        }

        with self._lock:
            self.tasks.append(new_task)
            self._save_local()

        self._async_cloud_op(self._cloud_set_task, new_task)
        return new_task

    def toggle_timer(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Inicia ou pausa o cronômetro de foco de uma tarefa."""
        updated_task = None
        with self._lock:
            for t in self.tasks:
                if t.get("id") == task_id:
                    # Se estiver rodando, pausa e acumula o tempo
                    if t.get("timer_running"):
                        if t.get("timer_started_at"):
                            try:
                                started = datetime.fromisoformat(t["timer_started_at"])
                                delta = int((datetime.now() - started).total_seconds())
                                t["elapsed_seconds"] = t.get("elapsed_seconds", 0) + max(0, delta)
                            except Exception:
                                pass
                        t["timer_running"] = False
                        t["timer_started_at"] = None
                    else:
                        # Se não estiver rodando, pausa outras e inicia esta
                        for other in self.tasks:
                            if other.get("timer_running") and other.get("id") != task_id:
                                if other.get("timer_started_at"):
                                    try:
                                        s = datetime.fromisoformat(other["timer_started_at"])
                                        d = int((datetime.now() - s).total_seconds())
                                        other["elapsed_seconds"] = other.get("elapsed_seconds", 0) + max(0, d)
                                    except Exception:
                                        pass
                                other["timer_running"] = False
                                other["timer_started_at"] = None

                        t["timer_running"] = True
                        t["timer_started_at"] = datetime.now().isoformat()

                    updated_task = dict(t)
                    break
            if updated_task:
                self._save_local()

        if updated_task:
            self._async_cloud_op(self._cloud_set_task, updated_task)
        return updated_task

    def get_task_current_elapsed(self, task: Dict[str, Any]) -> int:
        """Calcula os segundos totais decorridos considerando tempo acumulado + tempo atual se rodando."""
        total = task.get("elapsed_seconds", 0)
        if task.get("timer_running") and task.get("timer_started_at"):
            try:
                started = datetime.fromisoformat(task["timer_started_at"])
                total += int((datetime.now() - started).total_seconds())
            except Exception:
                pass
        return max(0, total)

    def toggle_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        updated_task = None
        with self._lock:
            for t in self.tasks:
                if t.get("id") == task_id:
                    new_state = not t.get("completed", False)
                    t["completed"] = new_state
                    
                    if new_state:
                        # Tarefa concluída: para o cronômetro se estiver rodando e grava a duração
                        if t.get("timer_running") and t.get("timer_started_at"):
                            try:
                                started = datetime.fromisoformat(t["timer_started_at"])
                                delta = int((datetime.now() - started).total_seconds())
                                t["elapsed_seconds"] = t.get("elapsed_seconds", 0) + max(0, delta)
                            except Exception:
                                pass
                        t["timer_running"] = False
                        t["timer_started_at"] = None

                        total_sec = t.get("elapsed_seconds", 0)
                        if total_sec > 0:
                            t["completed_duration"] = format_duration(total_sec)
                    else:
                        # Tarefa reaberta
                        t["timer_running"] = False
                        t["timer_started_at"] = None

                    updated_task = dict(t)
                    break
            if updated_task:
                self._save_local()

        if updated_task:
            self._async_cloud_op(self._cloud_set_task, updated_task)
        return updated_task

    def delete_task(self, task_id: str) -> bool:
        deleted = False
        with self._lock:
            initial_len = len(self.tasks)
            self.tasks = [t for t in self.tasks if t.get("id") != task_id]
            if len(self.tasks) < initial_len:
                self._save_local()
                deleted = True

        if deleted:
            self._async_cloud_op(self._cloud_delete_task, task_id)
        return deleted

    def clear_completed(self) -> int:
        completed_ids = []
        with self._lock:
            initial_len = len(self.tasks)
            completed_ids = [t.get("id") for t in self.tasks if t.get("completed", False)]
            self.tasks = [t for t in self.tasks if not t.get("completed", False)]
            removed_count = initial_len - len(self.tasks)
            if removed_count > 0:
                self._save_local()

        if completed_ids:
            self._async_cloud_op(self._cloud_batch_delete, completed_ids)
        return len(completed_ids)

    def find_task_by_title_match(self, search_text: str) -> Optional[Dict[str, Any]]:
        if not search_text:
            return None
        search_norm = search_text.lower().strip()
        with self._lock:
            for t in self.tasks:
                title_norm = t["title"].lower()
                if search_norm in title_norm or title_norm in search_norm:
                    return t
        return None
