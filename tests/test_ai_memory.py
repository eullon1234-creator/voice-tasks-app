import unittest
import os
import json
from pathlib import Path
from unittest.mock import MagicMock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_memory_engine import AIMemoryEngine

class TestAIMemoryEngine(unittest.TestCase):
    def setUp(self):
        self.test_file = Path(__file__).resolve().parent / "temp_ai_memory.json"
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        self.engine = AIMemoryEngine(memory_file=self.test_file)

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_default_memory_structure(self):
        memory = self.engine.memory
        self.assertEqual(memory["user_name"], "Eullon")
        self.assertIn("work_context", memory)
        self.assertIn("personal_habits", memory)
        self.assertIn("goals", memory)
        self.assertIn("preferences", memory)

    def test_add_and_remove_fact_manually(self):
        self.engine.add_fact_manually("work_context", "Coordena cronogramas semanais na GEL")
        self.assertIn("Coordena cronogramas semanais na GEL", self.engine.memory["work_context"])
        
        # Test persistence
        with open(self.test_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.assertIn("Coordena cronogramas semanais na GEL", data["work_context"])

        # Test remove
        idx = self.engine.memory["work_context"].index("Coordena cronogramas semanais na GEL")
        removed = self.engine.remove_fact("work_context", idx)
        self.assertTrue(removed)
        self.assertNotIn("Coordena cronogramas semanais na GEL", self.engine.memory["work_context"])

    def test_chat_with_copilot_and_task_suggestion(self):
        mock_groq = MagicMock()
        mock_groq.is_configured.return_value = True
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content="Com certeza! Vamos agendar isso. [CRIAR_TAREFA: Alinhar com diretoria | alta | Trabalho | 15:00]"))
        ]
        mock_groq._client.chat.completions.create.return_value = mock_completion

        engine = AIMemoryEngine(groq_client=mock_groq, memory_file=self.test_file)
        res = engine.chat_with_copilot("Preciso falar com a diretoria amanhã", [])

        self.assertIn("Com certeza", res["reply"])
        suggested = res["suggested_task"]
        self.assertIsNotNone(suggested)
        self.assertEqual(suggested["title"], "Alinhar com diretoria")
        self.assertEqual(suggested["priority"], "alta")
        self.assertEqual(suggested["category"], "Trabalho")
        self.assertEqual(suggested["due_time"], "15:00")

    def test_background_learning_extraction(self):
        mock_groq = MagicMock()
        mock_groq.is_configured.return_value = True
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content=json.dumps({
                "new_preferences": ["Gosta de tomar café sem açúcar após o almoço"],
                "new_work_context": [],
                "new_personal_habits": [],
                "new_goals": []
            })))
        ]
        mock_groq._client.chat.completions.create.return_value = mock_completion

        engine = AIMemoryEngine(groq_client=mock_groq, memory_file=self.test_file)
        engine._extract_facts_worker("Hoje comecei a tomar café sem açúcar depois do almoço e curti", "Legal!")

        self.assertIn("Gosta de tomar café sem açúcar após o almoço", engine.memory["preferences"])

    def test_generate_daily_mission(self):
        mock_groq = MagicMock()
        mock_groq.is_configured.return_value = True
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content=json.dumps({
                "tip": "Mantenha o foco nos relatórios da GEL hoje!",
                "task_title": "Finalizar medições de campo",
                "priority": "alta",
                "category": "Trabalho",
                "due_time": "14:00"
            })))
        ]
        mock_groq._client.chat.completions.create.return_value = mock_completion

        engine = AIMemoryEngine(groq_client=mock_groq, memory_file=self.test_file)
        mission = engine.generate_daily_mission([])
        self.assertIn("GEL", mission["tip"])
        self.assertEqual(mission["task"]["title"], "Finalizar medições de campo")
        self.assertEqual(mission["task"]["priority"], "alta")

if __name__ == "__main__":
    unittest.main()
