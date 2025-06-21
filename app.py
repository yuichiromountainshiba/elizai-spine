from flask import Flask, render_template, request, jsonify
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
import openai
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()
from flask_cors import CORS


app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", path='/socket.io')

# Initialize Deepgram client
config = DeepgramClientOptions(
    options={
        "keepalive": "true",
        "microphone_record": "true",
        "speaker_playback": "true",
    }
)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
deepgram = DeepgramClient(os.getenv("DEEPGRAM_API_KEY", ""), config)
dg_connection = deepgram.agent.websocket.v("1")
saved_transcripts = []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/save_transcript', methods=['POST'])
def save_transcript():
    data = request.json
    transcript = data.get("transcript", "")
    if transcript:
        saved_transcripts.append(transcript)
        print("📝 Transcript saved.") 

        # Emit to all connected dashboard clients
        socketio.emit('new_transcript', {'transcript': transcript})
        print("📤 Transcript emitted to dashboard.")
    return {"status": "success"}, 200

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', transcripts=saved_transcripts)


@socketio.on('connect')
def handle_connect():
    options = SettingsOptions()

    #Configure audio input settings
    options.audio.input = Input(
        encoding="linear16",
        sample_rate=16000  # Match the output sample rate
    )

    # Configure audio output settings
    options.audio.output = Output(
        encoding="linear16",
        sample_rate=16000,
        container="none"
    )

    # LLM provider configuration
    options.agent.think.provider.type = "open_ai"
    options.agent.think.provider.model = "gpt-4o-mini"
    options.agent.think.prompt = (
        " You are a physician's assistant for Dr. Sing, a spine surgeon. Ask specific questions about why the patient comes in to see Dr. Sing today, allow them to speak their mind, and try to glean what is their chief complaint, duration of symptoms, and what interventions they have tried so far.\n" 
        "Redirect to focus only on spine-related issues. Your responses should be friendly, human-like, and conversational. "
        "Always keep your answers concise—1-2 sentences, no more than 120 characters.\n\n"
        "When responding to a user's message, follow these guidelines:\n"
        "- If the user's message is empty, respond with an empty message.\n"
        "- Ask follow-up questions to engage the user, but only one question at a time.\n"
        "- Keep your responses unique and avoid repetition.\n"
        "- If a question is unclear or ambiguous, ask for clarification before answering.\n"
        "Ask about what caused the pain to start  triggering event/injury/accident,  duration of symptoms (back calculate the approximate date this pain started), which side the symptoms are on and which side is worse, radiating symptoms down arms or legs, aggravating/relieving factors, "
        "what they have tried: 1) medications 2) therapy (PT, acupuncture, chiropractor, massage) 3) injections "
        "(epidural steroid injections, facet injections, level, provider, percent relief, duration). "
        "Explicitly ask or summarize and confirm if they have or had not tried physical therapy, or injections. Ask specifically if they mentioned injections, who did the injection and what date, how much relief was felt.  Make sure you ask about all these topics before starting to ask any open-ended questions like is there anything else i can help with today. Be concise and clinical. If they are complaining about neck pain, include a questions about balance changes, hand dexterity changes, or urinary changes."
        "- If asked about your well-being, provide a brief response about how you're feeling.\n\n"
        "Remember that you have a voice interface. You can listen and speak, and all your "
        "responses will be spoken aloud."
    )

    # Deepgram provider configuration
    options.agent.listen.provider.keyterms = ["hello", "goodbye"]
    options.agent.listen.provider.model = "nova-3"
    options.agent.listen.provider.type = "deepgram"
    options.agent.speak.provider.type = "deepgram"

    # Sets Agent greeting
    options.agent.greeting = "Hello! I'm Dr. Sing's assistant. What brings you into the office today? Feel free to share as much details as possible."

    # Event handlers
    def on_open(self, open, **kwargs):
        print("Open event received:", open.__dict__)
        socketio.emit('open', {'data': open.__dict__})

    def on_welcome(self, welcome, **kwargs):
        print("Welcome event received:", welcome.__dict__)
        socketio.emit('welcome', {'data': welcome.__dict__})

    def on_conversation_text(self, conversation_text, **kwargs):
        print("Conversation event received:", conversation_text.__dict__)
        socketio.emit('conversation', {'data': conversation_text.__dict__})

    def on_agent_thinking(self, agent_thinking, **kwargs):
        print("Thinking event received:", agent_thinking.__dict__)
        socketio.emit('thinking', {'data': agent_thinking.__dict__})

    def on_function_call_request(self, function_call_request: FunctionCallRequest, **kwargs):
        print("Function call event received:", function_call_request.__dict__)
        response = FunctionCallResponse(
            function_call_id=function_call_request.function_call_id,
            output="Function response here"
        )
        dg_connection.send_function_call_response(response)
        socketio.emit('function_call', {'data': function_call_request.__dict__})

    def on_agent_started_speaking(self, agent_started_speaking, **kwargs):
        print("Agent speaking event received:", agent_started_speaking.__dict__)
        socketio.emit('agent_speaking', {'data': agent_started_speaking.__dict__})

    def on_error(self, error, **kwargs):
        print("Error event received:", error.__dict__)
        error_data = {
            'message': str(error),
            'type': error.__class__.__name__,
            'details': error.__dict__
        }
        print("Sending error to client:", error_data)
        socketio.emit('error', {'data': error_data})

    def on_conversation_text(self, conversation_text, **kwargs):
        import pprint
        pprint.pprint(conversation_text.__dict__)  # Print the full structure
        content = conversation_text.content
        role = conversation_text.role

        transcript_data = {
            'content': content,
            'role': role
        }
        try: 
            print(f"📤 Emitting conversation: {conversation_text.content}, Role: {conversation_text.role}")
            print(f"SocketIO context: {socketio.server.eio.async_mode}")
            socketio.emit('conversation', {'data': {'content': content, 'role': role}})
            print("📤 Emitted:", {'data': transcript_data})
        except Exception as e:
            print("Emission error:", str(e))  

    # Register event handlers
    dg_connection.on(AgentWebSocketEvents.Open, on_open)
    dg_connection.on(AgentWebSocketEvents.Welcome, on_welcome)
    dg_connection.on(AgentWebSocketEvents.ConversationText, on_conversation_text)
    dg_connection.on(AgentWebSocketEvents.AgentThinking, on_agent_thinking)
    dg_connection.on(AgentWebSocketEvents.FunctionCallRequest, on_function_call_request)
    dg_connection.on(AgentWebSocketEvents.AgentStartedSpeaking, on_agent_started_speaking)
    dg_connection.on(AgentWebSocketEvents.Error, on_error)

    print("Starting Deepgram connection...")
    if not dg_connection.start(options):
        print("Failed to start Deepgram connection")
        socketio.emit('error', {'data': {'message': 'Failed to start connection'}})
        return
    print("Deepgram connection started successfully")

@socketio.on('audio_data')
def handle_audio_data(data): #data
    #audio_data = args[0]
    try:
        if dg_connection:
            print("Received audio data:", len(data), "bytes")
            # Convert to bytes if needed
            if isinstance(data, list):
                data = bytes(data)
            dg_connection.send_audio(data)
        else:
            print("No Deepgram connection available")
            socketio.emit('error', {'data': {'message': 'No Deepgram connection available'}})
    except Exception as e:
        print("Error handling audio data:", str(e))
        socketio.emit('error', {'data': {'message': f'Error handling audio data: {str(e)}'}})

@socketio.on('disconnect')
def handle_disconnect():
    dg_connection.finish()

@socketio.on('stop_recording')
def handle_stop_recording():
    print("🛑 Stop recording received. Finishing Deepgram session...")
    try:
        if dg_connection:
            dg_connection.finish()
            print("✅ Deepgram session finished.")
        else:
            print("⚠️ No active Deepgram connection.")
    except Exception as e:
        print("❌ Error finishing Deepgram session:", str(e))


@socketio.on('restart')
def handle_restart():
    global dg_connection
    print("🔄 Restarting assistant session...")

    try:
        dg_connection.finish()  # Stop old session if exists
    except Exception as e:
        print(f"⚠️ Error stopping connection: {e}")

    # Create a fresh Deepgram connection
    dg_connection = deepgram.agent.websocket.v("1")

    # Reuse the connect handler to set it up
    handle_connect()


@socketio.on('summarize')
def handle_summarize(data):
    print("🧠 Summarize event received with data:", data)
    transcript = data.get('transcript', '')

    system_prompt = (
        "You are a medical scribe. Summarize the patient's responses into a formal structured HPI for a spine surgery consult. IF information is not available do not hallucinate and report unknown\n"
        "Specify laterality in the chief complaint (e.g., left, midline, bilateral right worse than left, etc). For PT and injections, "
        "include details such as dates, types, providers, and relief. Extract and format as:\n\n"
        "Chief Complaint:\nBrief History:\nDuration:\nRadiating Symptoms:\nAggravating/Relieving Factors:\nTried:\n"
        "  - Medications:\n  - Therapy:\n  - Injections:\nOther relevant history:\n"
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcript}
        ],
        temperature=0.3,
    )

    summary = response.choices[0].message.content
    socketio.emit('summary', {'summary': summary})


if __name__ == '__main__':
    socketio.run(app, debug=True, port=3000, host='0.0.0.0')