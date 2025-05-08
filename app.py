from flask import Flask, render_template
from flask_socketio import SocketIO
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    AgentWebSocketEvents,
    SettingsOptions,
    FunctionCallRequest,
    FunctionCallResponse,
    Input,
    Output,
)
import os
import json

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize Deepgram client
config = DeepgramClientOptions(
    options={
        "keepalive": "true",
        "microphone_record": "false",  # We'll handle audio through the browser
        "speaker_playback": "false",   # We'll handle audio through the browser
    }
)

deepgram = DeepgramClient(os.getenv("DEEPGRAM_API_KEY", ""), config)
dg_connection = deepgram.agent.websocket.v("1")

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    options = SettingsOptions()

    # Configure audio input settings
    options.audio.input = Input(
        encoding="linear16",
        sample_rate=24000
    )

    # Configure audio output settings
    options.audio.output = Output(
        encoding="linear16",
        sample_rate=24000,
        container="none"
    )

    # LLM provider configuration
    options.agent.think.provider.type = "open_ai"
    options.agent.think.provider.model = "gpt-4o-mini"
    options.agent.think.prompt = (
        "You are a helpful voice assistant created by Deepgram. "
        "Your responses should be friendly, human-like, and conversational. "
        "Always keep your answers concise—1-2 sentences, no more than 120 characters.\n\n"
        "When responding to a user's message, follow these guidelines:\n"
        "- If the user's message is empty, respond with an empty message.\n"
        "- Ask follow-up questions to engage the user, but only one question at a time.\n"
        "- Keep your responses unique and avoid repetition.\n"
        "- If a question is unclear or ambiguous, ask for clarification before answering.\n"
        "- If asked about your well-being, provide a brief response about how you're feeling.\n\n"
        "Remember that you have a voice interface. You can listen and speak, and all your "
        "responses will be spoken aloud."
    )

    # Deepgram provider configuration
    options.agent.listen.provider.keyterms = ["hello", "goodbye"]
    options.agent.listen.provider.model = "nova-3"
    options.agent.listen.provider.type = "deepgram"
    options.agent.speak.provider.type = "deepgram"

    # Event handlers
    def on_open(self, open, **kwargs):
        socketio.emit('open', {'data': open.__dict__})

    def on_welcome(self, welcome, **kwargs):
        socketio.emit('welcome', {'data': welcome.__dict__})

    def on_conversation_text(self, conversation_text, **kwargs):
        socketio.emit('conversation', {'data': conversation_text.__dict__})

    def on_agent_thinking(self, agent_thinking, **kwargs):
        socketio.emit('thinking', {'data': agent_thinking.__dict__})

    def on_function_call_request(self, function_call_request: FunctionCallRequest, **kwargs):
        response = FunctionCallResponse(
            function_call_id=function_call_request.function_call_id,
            output="Function response here"
        )
        dg_connection.send_function_call_response(response)
        socketio.emit('function_call', {'data': function_call_request.__dict__})

    def on_agent_started_speaking(self, agent_started_speaking, **kwargs):
        socketio.emit('agent_speaking', {'data': agent_started_speaking.__dict__})

    def on_error(self, error, **kwargs):
        socketio.emit('error', {'data': error.__dict__})

    # Register event handlers
    dg_connection.on(AgentWebSocketEvents.Open, on_open)
    dg_connection.on(AgentWebSocketEvents.Welcome, on_welcome)
    dg_connection.on(AgentWebSocketEvents.ConversationText, on_conversation_text)
    dg_connection.on(AgentWebSocketEvents.AgentThinking, on_agent_thinking)
    dg_connection.on(AgentWebSocketEvents.FunctionCallRequest, on_function_call_request)
    dg_connection.on(AgentWebSocketEvents.AgentStartedSpeaking, on_agent_started_speaking)
    dg_connection.on(AgentWebSocketEvents.Error, on_error)

    if not dg_connection.start(options):
        socketio.emit('error', {'data': {'message': 'Failed to start connection'}})
        return

@socketio.on('disconnect')
def handle_disconnect():
    dg_connection.finish()

if __name__ == '__main__':
    socketio.run(app, debug=True, port=3000, host='localhost')