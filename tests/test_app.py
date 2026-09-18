import unittest
import os
import json
import io
import wave
import numpy as np
from unittest.mock import MagicMock, patch

# Adiciona diretório pai ao sys.path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage import TaskStorage
from groq_client import GroqClient, SYSTEM_PROMPT
from audio_recorder import AudioRecorder

class TestTaskStorage(unittest.TestCase):
    def setUp(self):
        self.test_file = Path(__file__).resolve().parent / "temp_tasks.json"
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        self.storage = TaskStorage(filepath=self.test_file)

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_add_and_get_tasks(self):
        t1 = self.storage.add_task(title="Ligar para o cliente", priority="alta", due_time="16h")
        self.assertEqual(t1["title"], "Ligar para o cliente")
        self.assertEqual(t1["priority"], "alta")
        self.assertEqual(t1["due_time"], "16h")
        self.assertFalse(t1["completed"])
        self.assertEqual(t1["id"], "t1")

        pending = self.storage.get_pending_tasks()
        self.assertEqual(len(pending), 1)

    def test_toggle_task(self):
        t1 = self.storage.add_task(title="Comprar café")
        self.assertFalse(t1["completed"])

        updated = self.storage.toggle_task(t1["id"])
        self.assertTrue(updated["completed"])
        self.assertEqual(len(self.storage.get_completed_tasks()), 1)
        self.assertEqual(len(self.storage.get_pending_tasks()), 0)

        # Toggle de volta
        updated2 = self.storage.toggle_task(t1["id"])
        self.assertFalse(updated2["completed"])
        self.assertEqual(len(self.storage.get_pending_tasks()), 1)

    def test_delete_and_clear_completed(self):
        t1 = self.storage.add_task("Tarefa 1")
        t2 = self.storage.add_task("Tarefa 2")
        t3 = self.storage.add_task("Tarefa 3")

        self.storage.toggle_task(t1["id"])
        self.storage.toggle_task(t2["id"])

        # Teste clear_completed
        cleared = self.storage.clear_completed()
        self.assertEqual(cleared, 2)
        self.assertEqual(len(self.storage.get_all_tasks()), 1)

        # Teste delete_task
        deleted = self.storage.delete_task(t3["id"])
        self.assertTrue(deleted)
        self.assertEqual(len(self.storage.get_all_tasks()), 0)

    def test_find_by_title_match(self):
        self.storage.add_task("Enviar relatório financeiro")
        match = self.storage.find_task_by_title_match("relatório")
        self.assertIsNotNone(match)
        self.assertEqual(match["title"], "Enviar relatório financeiro")

    def test_task_category_and_filter(self):
        t1 = self.storage.add_task("Planejamento sprint", category="Trabalho")
        t2 = self.storage.add_task("Treino de perna", category="Pessoal")
        t3 = self.storage.add_task("Capítulo 4 de IA", category="Estudos")
        t4 = self.storage.add_task("Comprar pão")  # Default Geral

        self.assertEqual(t1["category"], "Trabalho")
        self.assertEqual(t2["category"], "Pessoal")
        self.assertEqual(t3["category"], "Estudos")
        self.assertEqual(t4["category"], "Geral")

        trabalho_tasks = self.storage.get_tasks_by_category("Trabalho")
        self.assertEqual(len(trabalho_tasks), 1)
        self.assertEqual(trabalho_tasks[0]["title"], "Planejamento sprint")

        all_tasks = self.storage.get_tasks_by_category("Todas")
        self.assertEqual(len(all_tasks), 4)

    def test_streak_and_daily_goal(self):
        from datetime import datetime
        t1 = self.storage.add_task("Tarefa de hoje")
        self.storage.toggle_task(t1["id"])  # Conclui hoje

        streak = self.storage.calculate_streak()
        self.assertGreaterEqual(streak, 1)

        goal = self.storage.get_daily_goal_progress(goal_minutes=60)
        self.assertIn("percentage", goal)
        self.assertIn("streak_days", goal)
        self.assertEqual(goal["streak_days"], streak)

    def test_due_reminders(self):
        from datetime import datetime
        now_hm = datetime.now().strftime("%H:%M")
        t = self.storage.add_task("Ligar agora", due_time=now_hm)
        
        due = self.storage.get_due_reminders()
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["id"], t["id"])

        self.storage.mark_reminded(t["id"])
        due_after = self.storage.get_due_reminders()
        self.assertEqual(len(due_after), 0)

    def test_concurrent_timers(self):
        t1 = self.storage.add_task("Ficar uma hora sem celular")
        t2 = self.storage.add_task("Fazer as OS das ferramentas")

        # Inicia timer da tarefa 1
        res1 = self.storage.toggle_timer(t1["id"])
        self.assertTrue(res1["timer_running"])

        # Inicia timer da tarefa 2 (ambas devem rodar ao mesmo tempo)
        res2 = self.storage.toggle_timer(t2["id"])
        self.assertTrue(res2["timer_running"])

        # Verifica se ambas continuam rodando simultaneamente
        all_tasks = {t["id"]: t for t in self.storage.get_all_tasks()}
        self.assertTrue(all_tasks[t1["id"]]["timer_running"])
        self.assertTrue(all_tasks[t2["id"]]["timer_running"])

        # Pausa tarefa 1, tarefa 2 continua rodando
        self.storage.toggle_timer(t1["id"])
        all_tasks = {t["id"]: t for t in self.storage.get_all_tasks()}
        self.assertFalse(all_tasks[t1["id"]]["timer_running"])
        self.assertTrue(all_tasks[t2["id"]]["timer_running"])


class TestGroqClientMock(unittest.TestCase):
    def setUp(self):
        self.client = GroqClient(api_key="gsk_test_mock_key")

    @patch("groq_client.Groq")
    def test_process_command_add(self, mock_groq_class):
        mock_instance = MagicMock()
        self.client._client = mock_instance

        # Mock da resposta do Llama 3.3
        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps({
            "action": "add",
            "task_id": None,
            "task_title": "Ligar pro cliente",
            "priority": "alta",
            "due_time": "16h",
            "feedback_message": "Tarefa adicionada com prioridade alta"
        })
        mock_instance.chat.completions.create.return_value.choices = [mock_choice]

        result = self.client.process_command("Anotar ligar pro cliente às 16h alta", [])
        self.assertEqual(result["action"], "add")
        self.assertEqual(result["task_title"], "Ligar pro cliente")
        self.assertEqual(result["priority"], "alta")
        self.assertEqual(result["due_time"], "16h")

    @patch("groq_client.Groq")
    def test_process_command_toggle_and_clear(self, mock_groq_class):
        mock_instance = MagicMock()
        self.client._client = mock_instance

        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps({
            "action": "clear_completed",
            "task_id": None,
            "task_title": "",
            "priority": "media",
            "due_time": None,
            "feedback_message": "Concluídas limpas"
        })
        mock_instance.chat.completions.create.return_value.choices = [mock_choice]

        result = self.client.process_command("Limpar tarefas concluídas", [])
        self.assertEqual(result["action"], "clear_completed")


class TestAudioRecorderMemory(unittest.TestCase):
    def test_wav_buffer_generation(self):
        recorder = AudioRecorder(sample_rate=16000, channels=1)
        
        # Simula gravação populando a fila com áudio sintético (1 segundo de onda senoidal)
        sample_rate = 16000
        t = np.linspace(0, 1.0, sample_rate, False)
        tone = np.sin(440 * t * 2 * np.pi)
        audio_int16 = (tone * 32767).astype(np.int16).reshape(-1, 1)

        recorder.is_recording = True
        recorder._audio_queue.put(audio_int16)

        wav_bytes = recorder.stop()
        self.assertIsNotNone(wav_bytes)
        self.assertGreater(len(wav_bytes), 1000)

        # Valida que os bytes gerados são um arquivo WAV válido
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)  # 16-bit
            self.assertEqual(wf.getframerate(), 16000)
            self.assertEqual(wf.getnframes(), 16000)


if __name__ == "__main__":
    unittest.main()
