# ⚡ Voice Sticky Notes & Tasks (Groq AI & Firebase)

> 🌐 **Acesse a Demonstração Web (GitHub Pages):** [https://eullon1234-creator.github.io/voice-tasks-app/](https://eullon1234-creator.github.io/voice-tasks-app/)
> 
> 📦 **Repositório GitHub:** [https://github.com/eullon1234-creator/voice-tasks-app](https://github.com/eullon1234-creator/voice-tasks-app)

Aplicativo desktop flutuante de anotações e tarefas (To-Do/Sticky Notes) focado em **alta produtividade, ultraleveza e controle por voz instantâneo**.

Projetado com janela *Always on Top*, design moderno Dark Mode e consumo reduzido de memória (**~35 a 55 MB de RAM**, bem abaixo do limite de 80 MB).

---

## 🌟 Principais Recursos

1. **Janela Flutuante Always on Top:**
   - Permanece sobreposta às suas outras janelas para anotações instantâneas enquanto você trabalha.
   - Botão de fixação (📌 / 📍) para alternar o modo sobreposto a qualquer momento.
   - Translucidez suave e estética moderna Dark Mode com cantos arredondados.
2. **Controle Instantâneo por Voz:**
   - **Atalho Global:** Pressione `Ctrl + Shift + Espaço` em qualquer lugar do Windows para começar a falar e pressione novamente para enviar.
   - **Botão Pulsante na UI:** Botão de microfone com animação pulsante e barra de nível de onda sonora em tempo real.
   - Gravação 100% em buffer de memória (`io.BytesIO`), sem arquivos temporários no disco e sem travar a interface.
3. **Inteligência Artificial (Groq Cloud):**
   - **STT:** `whisper-large-v3` com parâmetro `pt` para transcrição veloz em português.
   - **LLM:** `llama-3.3-70b-versatile` com estruturação estrita em JSON para interpretação de intenções complexas.
4. **Organização Visual:**
   - Listas divididas em **"A Fazer"** e **"Concluídas"**.
   - Badges coloridos de prioridade (**Alta** em vermelho, **Média** em amarelo, **Baixa** em verde).
   - Horários de entrega (*Due Time*) extraídos automaticamente.
   - Checkbox rápido e botão de exclusão manual.
   - Botão para limpar todas as tarefas concluídas.
5. **Persistência Local Automática:**
   - Gravação atômica em `tasks.json`.

---

## 🎤 Exemplos de Comandos de Voz Suportados

| Comando Falado | Ação Realizada |
| :--- | :--- |
| *"Anotar ligar pro cliente às 16h, prioridade alta"* | Cria nova tarefa com prioridade Alta e horário 16h |
| *"Comprar café amanhã de manhã"* | Cria nova tarefa com prioridade normal e horário extraído |
| *"Marca a tarefa do relatório como pronta"* | Localiza a tarefa e marca como concluída |
| *"Apaga o lembrete de comprar café"* | Remove a tarefa correspondente |
| *"Limpa tudo o que já foi concluído"* | Remove todas as tarefas da seção Concluídas |

---

## 📁 Estrutura do Projeto

```
voice_notes_app/
│
├── config.py              # Configurações globais (Cores, Áudio 16kHz, Modelos, Atalho)
├── storage.py             # CRUD e persistência atômica em tasks.json
├── audio_recorder.py      # Captura de microfone assíncrona em memória WAV
├── groq_client.py         # Cliente Groq Cloud (Whisper STT + Llama 3.3 JSON)
├── ui/
│   ├── __init__.py
│   ├── components.py      # Badges, Cards de tarefas e Mic Button com pulso
│   └── app_window.py      # Janela principal CustomTkinter (Always on Top)
├── main.py                # Inicializador da aplicação e Hotkey Global
├── requirements.txt       # Dependências Python
├── .env.example           # Modelo para chave de API
└── README.md              # Este guia
```

---

## 🚀 Como Executar

### 1. Pré-requisitos
- Python 3.10 ou superior
- Microfone padrão configurado no Windows

### 2. Instalação das Dependências
No terminal, dentro da pasta do projeto:

```bash
pip install -r requirements.txt
```

### 3. Configuração da Groq API Key
Obtenha sua chave gratuita em [console.groq.com](https://console.groq.com/keys).

Você tem duas formas fáceis de configurar:
- **Opção A:** Crie um arquivo `.env` baseado no `.env.example`:
  ```env
  GROQ_API_KEY=gsk_sua_chave_aqui
  ```
- **Opção B:** Inicie o aplicativo e clique no botão **"🔑 API"** no canto superior direito para colar sua chave diretamente pela interface!

### 4. Executando o Aplicativo
```bash
python main.py
```
