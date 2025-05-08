from flask import Flask, render_template, Response
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    AgentWebSocketEvents,
    SettingsOptions,
    FunctionCallRequest,
    FunctionCallResponse,
)
import os
import json

app = Flask(__name__)

# Initialize Deepgram client
config = DeepgramClientOptions(
    options={
        "keepalive": "true",
        "microphone_record": "true",
        "speaker_playback": "true",
    }
)

deepgram = DeepgramClient(os.getenv("DEEPGRAM_API_KEY", ""), config)
dg_connection = deepgram.agent.websocket.v("1")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/ws')
def websocket():
    def generate():
        options = SettingsOptions()
        options.agent.think.provider.type = "open_ai"
        options.agent.think.provider.model = "gpt-4-mini"
        options.agent.think.prompt = "You are a helpful AI assistant."
        options.greeting = "Hello, this is a text to speech example using Deepgram."
        options.agent.listen.provider.keyterms = ["hello", "goodbye"]
        options.agent.listen.provider.model = "nova-3"
        options.agent.listen.provider.type = "deepgram"
        options.language = "en"

        def on_open(self, open, **kwargs):
            yield f"data: {json.dumps({'type': 'open', 'data': open})}\n\n"

        def on_welcome(self, welcome, **kwargs):
            yield f"data: {json.dumps({'type': 'welcome', 'data': welcome})}\n\n"

        def on_conversation_text(self, conversation_text, **kwargs):
            yield f"data: {json.dumps({'type': 'conversation', 'data': conversation_text})}\n\n"

        def on_agent_thinking(self, agent_thinking, **kwargs):
            yield f"data: {json.dumps({'type': 'thinking', 'data': agent_thinking})}\n\n"

        def on_function_call_request(self, function_call_request: FunctionCallRequest, **kwargs):
            response = FunctionCallResponse(
                function_call_id=function_call_request.function_call_id,
                output="Function response here"
            )
            dg_connection.send_function_call_response(response)
            yield f"data: {json.dumps({'type': 'function_call', 'data': function_call_request})}\n\n"

        def on_agent_started_speaking(self, agent_started_speaking, **kwargs):
            yield f"data: {json.dumps({'type': 'agent_speaking', 'data': agent_started_speaking})}\n\n"

        def on_error(self, error, **kwargs):
            yield f"data: {json.dumps({'type': 'error', 'data': error})}\n\n"

        # Register event handlers
        dg_connection.on(AgentWebSocketEvents.Open, on_open)
        dg_connection.on(AgentWebSocketEvents.Welcome, on_welcome)
        dg_connection.on(AgentWebSocketEvents.ConversationText, on_conversation_text)
        dg_connection.on(AgentWebSocketEvents.AgentThinking, on_agent_thinking)
        dg_connection.on(AgentWebSocketEvents.FunctionCallRequest, on_function_call_request)
        dg_connection.on(AgentWebSocketEvents.AgentStartedSpeaking, on_agent_started_speaking)
        dg_connection.on(AgentWebSocketEvents.Error, on_error)

        if not dg_connection.start(options):
            yield f"data: {json.dumps({'type': 'error', 'data': 'Failed to start connection'})}\n\n"
            return

        try:
            while True:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        finally:
            dg_connection.finish()

    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True)