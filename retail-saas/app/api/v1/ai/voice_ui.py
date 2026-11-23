def get_voice_assistant_html() -> str:
    return """<!DOCTYPE html>
<html lang="mr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Retail-OS | AI Real Voice Copilot (स्मार्ट रिटेल व्हॉईस असिस्टंट)</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+Devanagari:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body {
            font-family: 'Noto Sans Devanagari', 'Inter', sans-serif;
            background: radial-gradient(circle at top, #0f172a 0%, #020617 100%);
            min-height: 100vh;
        }
        @keyframes pulse-ring {
            0% { transform: scale(0.95); opacity: 0.8; }
            50% { transform: scale(1.2); opacity: 0.3; }
            100% { transform: scale(0.95); opacity: 0.8; }
        }
        .mic-active {
            animation: pulse-ring 1.8s infinite ease-in-out;
            box-shadow: 0 0 35px rgba(239, 68, 68, 0.7);
        }
        .sound-wave-bar {
            animation: wave 1s infinite ease-in-out alternate;
        }
        @keyframes wave {
            0% { height: 8px; }
            100% { height: 36px; }
        }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: #0f172a; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
    </style>
</head>
<body class="text-slate-100 flex flex-col justify-between">

    <!-- Top Navigation Header -->
    <header class="border-b border-slate-800 bg-slate-900/70 backdrop-blur-md px-6 py-4 flex flex-wrap items-center justify-between gap-4 sticky top-0 z-40">
        <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-400 flex items-center justify-center shadow-lg shadow-teal-500/20">
                <svg class="w-6 h-6 text-slate-950 font-bold" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 02-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"></path>
                </svg>
            </div>
            <div>
                <h1 class="text-lg font-bold text-white tracking-wide flex items-center gap-2">
                    Retail-OS AI Voice Copilot
                    <span class="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">Gemini 1.5 Live</span>
                </h1>
                <p class="text-xs text-slate-400">बोलून विचारा आणि आवाजात उत्तर ऐका (Real-Time Voice Assistant)</p>
            </div>
        </div>

        <!-- Controls: Auth Pill, Language & Audio Toggle -->
        <div class="flex items-center gap-3 flex-wrap">
            
            <!-- Auth / Login Button -->
            <button id="authBtn" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition bg-amber-950/60 border-amber-600/50 text-amber-300 hover:bg-amber-900/70" title="लॉगिन करा किंवा टोकन जोडा">
                <span id="authDot">🟡</span>
                <span id="authLabel">लॉगिन आवश्यक (Connect)</span>
            </button>

            <!-- Language Selector -->
            <div class="flex items-center bg-slate-800 border border-slate-700 rounded-lg px-2 py-1 text-xs">
                <span class="text-slate-400 mr-2">भाषा:</span>
                <select id="langSelect" class="bg-transparent text-white font-medium focus:outline-none cursor-pointer">
                    <option value="mr-IN" selected class="bg-slate-900">मराठी (Marathi)</option>
                    <option value="hi-IN" class="bg-slate-900">हिंदी (Hindi)</option>
                    <option value="en-IN" class="bg-slate-900">English (India)</option>
                </select>
            </div>

            <!-- Auto-Speak Toggle Button -->
            <button id="toggleSpeakBtn" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition bg-emerald-950/60 border-emerald-600/50 text-emerald-300 hover:bg-emerald-900/70" title="उत्तर आवाजात ऐकावे की नाही">
                <span id="speakerIcon">🔊</span>
                <span id="speakerLabel">व्हॉईस चालू (Voice ON)</span>
            </button>

            <!-- Stop Speaking Button -->
            <button id="stopAudioBtn" class="hidden px-2.5 py-1.5 rounded-lg border border-red-500/40 bg-red-950/50 text-red-300 text-xs font-medium hover:bg-red-900/60 transition">
                ⏹️ आवाज थांबवा
            </button>
        </div>
    </header>

    <!-- Main Container -->
    <main class="max-w-4xl w-full mx-auto px-4 py-6 flex-1 flex flex-col justify-between">

        <!-- Conversation History Area -->
        <div id="chatHistory" class="flex-1 overflow-y-auto space-y-4 pr-1 max-h-[58vh]">
            <!-- Welcome Bot Message -->
            <div class="flex items-start gap-3 bg-slate-900/90 border border-slate-800 p-4 rounded-2xl shadow-md">
                <div class="w-9 h-9 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center shrink-0">
                    🤖
                </div>
                <div class="flex-1">
                    <div class="flex items-center justify-between mb-1">
                        <span class="font-semibold text-sm text-emerald-400">Retail-OS AI Copilot</span>
                        <span class="text-[11px] text-slate-500">आत्ता</span>
                    </div>
                    <p class="text-sm text-slate-200 leading-relaxed">
                        नमस्कार! मी तुमचा <strong>स्मार्ट रिटेल असिस्टंट</strong> आहे. खालील मायक्रोफोन बटण दाबा आणि तुमच्या दुकानाचा कोणताही प्रश्न थेट आवाजात विचारा. मी तुमच्या दुकानाचा डेटा तपासून मराठीत <strong>बोलून उत्तर देईन!</strong>
                    </p>
                    <div class="mt-3 flex flex-wrap gap-2 text-xs">
                        <button onclick="askPreset('आजचा एकूण गल्ला किती झाला?')" class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-2.5 py-1 rounded-md border border-slate-700 transition">
                            💸 आजचा एकूण गल्ला?
                        </button>
                        <button onclick="askPreset('कोणत्या वस्तूंचा स्टॉक संपत आला आहे?')" class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-2.5 py-1 rounded-md border border-slate-700 transition">
                            📦 कमी स्टॉक अलर्ट?
                        </button>
                        <button onclick="askPreset('१००० रुपयांपेक्षा जास्त उधारी कोणाची बाकी आहे?')" class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-2.5 py-1 rounded-md border border-slate-700 transition">
                            📋 उधारी बाकी खातेदार?
                        </button>
                        <button onclick="askPreset('दिवाळीसाठी मला कोणत्या ५ प्रॉडक्ट्सचा स्टॉक जास्त मागवावा लागेल?')" class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-2.5 py-1 rounded-md border border-slate-700 transition">
                            🪔 सण/दिवाळी स्टॉक सल्ला?
                        </button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Center Microphone Interaction Panel -->
        <div class="mt-6 border-t border-slate-800/80 pt-6 flex flex-col items-center">
            
            <!-- Audio Waves (shown when listening or speaking) -->
            <div id="audioWaveContainer" class="hidden flex items-center justify-center gap-1.5 h-10 mb-2">
                <div class="w-1.5 bg-emerald-400 rounded-full sound-wave-bar" style="animation-delay: 0.1s"></div>
                <div class="w-1.5 bg-teal-400 rounded-full sound-wave-bar" style="animation-delay: 0.3s"></div>
                <div class="w-1.5 bg-cyan-400 rounded-full sound-wave-bar" style="animation-delay: 0.2s"></div>
                <div class="w-1.5 bg-blue-400 rounded-full sound-wave-bar" style="animation-delay: 0.4s"></div>
                <div class="w-1.5 bg-indigo-400 rounded-full sound-wave-bar" style="animation-delay: 0.2s"></div>
                <div class="w-1.5 bg-emerald-400 rounded-full sound-wave-bar" style="animation-delay: 0.5s"></div>
            </div>

            <!-- Status Indicator -->
            <div id="statusIndicator" class="text-sm font-medium text-slate-300 mb-3 text-center">
                माइक बटण दाबा आणि थेट बोला...
            </div>

            <!-- Big Glowing Microphone Button -->
            <div class="relative flex items-center justify-center">
                <button id="micBtn" class="w-20 h-20 rounded-full bg-gradient-to-tr from-emerald-600 via-teal-500 to-cyan-500 text-white flex items-center justify-center shadow-xl shadow-teal-500/30 hover:scale-105 active:scale-95 transition-all duration-200 z-10 focus:outline-none">
                    <svg id="micIcon" class="w-9 h-9" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 02-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"></path>
                    </svg>
                </button>
            </div>

            <!-- Text Fallback Input Bar -->
            <form id="textForm" class="w-full max-w-xl mt-4 flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-xl px-3 py-1.5 shadow-inner">
                <input id="textInput" type="text" placeholder="किंवा येथे प्रश्न टाईप करा (उदा. आजची विक्री किती?)..." class="flex-1 bg-transparent border-none text-sm text-slate-100 placeholder-slate-500 focus:outline-none px-2 py-1">
                <button type="submit" class="bg-emerald-600 hover:bg-emerald-500 text-white p-2 rounded-lg transition shrink-0" title="Send">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"></path>
                    </svg>
                </button>
            </form>
        </div>

    </main>

    <!-- Footer -->
    <footer class="border-t border-slate-900 py-3 text-center text-xs text-slate-500">
        Retail-OS Voice Intelligence &bull; Powered by Google Gemini 1.5 & Web Speech Engine
    </footer>

    <!-- Auth / Login Modal -->
    <div id="authModal" class="hidden fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50">
        <div class="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 shadow-2xl relative">
            <button id="closeAuthModal" class="absolute top-4 right-4 text-slate-400 hover:text-white text-xl font-bold">&times;</button>
            <h3 class="text-base font-bold text-white flex items-center gap-2 mb-1">
                <span>🔑</span> Retail-OS ऑथेंटिकेशन (Login / Token)
            </h3>
            <p class="text-xs text-slate-400 mb-4">
                व्हॉईस असिस्टंटला तुमच्या दुकानाचा डेटा (विक्री, स्टॉक, उधारी) ॲक्सेस करण्यासाठी लॉगिन आवश्यक आहे.
            </p>

            <!-- Tabs -->
            <div class="flex border-b border-slate-800 mb-4 text-xs font-semibold">
                <button id="tabLogin" type="button" class="pb-2 px-3 border-b-2 border-emerald-500 text-emerald-400">१. थेट लॉगिन करा (Email & Password)</button>
                <button id="tabToken" type="button" class="pb-2 px-3 text-slate-400 hover:text-white">२. टोकन पेस्ट करा (Swagger UI)</button>
            </div>

            <!-- Login Form Panel -->
            <form id="loginForm" class="space-y-3">
                <div>
                    <label class="block text-xs text-slate-300 mb-1">ईमेल (Email):</label>
                    <input id="loginEmail" type="email" placeholder="admin@example.com" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500" required>
                </div>
                <div>
                    <label class="block text-xs text-slate-300 mb-1">पासवर्ड (Password):</label>
                    <input id="loginPassword" type="password" placeholder="••••••••" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500" required>
                </div>
                <div id="loginError" class="hidden text-xs text-red-400 bg-red-950/40 p-2.5 rounded border border-red-800/40"></div>
                <button type="submit" id="loginSubmitBtn" class="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-medium py-2 rounded-lg text-sm transition flex items-center justify-center gap-2">
                    <span>लॉगिन करा आणि व्हॉईस सुरू करा</span>
                </button>
            </form>

            <!-- Token Paste Panel -->
            <div id="tokenPanel" class="hidden space-y-3">
                <p class="text-xs text-slate-400 leading-relaxed">
                    डाव्या बाजूला उघडलेल्या <strong>Swagger UI</strong> टॅबमधून किंवा पोस्टमनवरून घेतलेला <code class="text-emerald-400 bg-slate-950 px-1 py-0.5 rounded">access_token</code> येथे पेस्ट करा:
                </p>
                <textarea id="tokenInput" rows="3" placeholder="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." class="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-white focus:outline-none focus:border-emerald-500 font-mono"></textarea>
                <button id="saveTokenBtn" type="button" class="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-medium py-2 rounded-lg text-sm transition">
                    टोकन सेव्ह करा
                </button>
            </div>
        </div>
    </div>

    <!-- Client-Side Real-Time Speech & Auth Logic -->
    <script>
        const micBtn = document.getElementById('micBtn');
        const micIcon = document.getElementById('micIcon');
        const statusIndicator = document.getElementById('statusIndicator');
        const audioWaveContainer = document.getElementById('audioWaveContainer');
        const chatHistory = document.getElementById('chatHistory');
        const langSelect = document.getElementById('langSelect');
        const toggleSpeakBtn = document.getElementById('toggleSpeakBtn');
        const speakerIcon = document.getElementById('speakerIcon');
        const speakerLabel = document.getElementById('speakerLabel');
        const stopAudioBtn = document.getElementById('stopAudioBtn');
        const textForm = document.getElementById('textForm');
        const textInput = document.getElementById('textInput');

        // Auth Elements
        const authBtn = document.getElementById('authBtn');
        const authDot = document.getElementById('authDot');
        const authLabel = document.getElementById('authLabel');
        const authModal = document.getElementById('authModal');
        const closeAuthModal = document.getElementById('closeAuthModal');
        const tabLogin = document.getElementById('tabLogin');
        const tabToken = document.getElementById('tabToken');
        const loginForm = document.getElementById('loginForm');
        const loginEmail = document.getElementById('loginEmail');
        const loginPassword = document.getElementById('loginPassword');
        const loginError = document.getElementById('loginError');
        const loginSubmitBtn = document.getElementById('loginSubmitBtn');
        const tokenPanel = document.getElementById('tokenPanel');
        const tokenInput = document.getElementById('tokenInput');
        const saveTokenBtn = document.getElementById('saveTokenBtn');

        let isListening = false;
        let autoSpeak = true;
        let recognition = null;
        let synth = window.speechSynthesis;
        let pendingQuestion = null;

        // Auto-capture token from URL if present (?token=...)
        const urlParams = new URLSearchParams(window.location.search);
        const tokenFromUrl = urlParams.get('token');
        if (tokenFromUrl) {
            localStorage.setItem('access_token', tokenFromUrl);
        }

        // Initialize Auth Status
        function updateAuthUI() {
            const token = localStorage.getItem('access_token');
            if (token) {
                authDot.innerText = '🟢';
                authLabel.innerText = 'कनेक्टेड (Connected)';
                authBtn.className = "flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition bg-emerald-950/60 border-emerald-600/50 text-emerald-300 hover:bg-emerald-900/70";
                authBtn.title = "कनेक्टेड आहे (लॉगआउट करण्यासाठी क्लिक करा)";
            } else {
                authDot.innerText = '🟡';
                authLabel.innerText = 'लॉगिन करा (Login to Connect)';
                authBtn.className = "flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-semibold transition bg-amber-950/70 border-amber-500/60 text-amber-300 hover:bg-amber-900/80 animate-pulse";
                authBtn.title = "दुकानाचा डेटा ॲक्सेस करण्यासाठी लॉगिन करा";
            }
        }
        updateAuthUI();

        // Auth Modal Handlers
        authBtn.addEventListener('click', () => {
            const token = localStorage.getItem('access_token');
            if (token) {
                if (confirm("तुम्ही आधीच कनेक्टेड आहात. लॉगआउट करून नवीन टोकन टाकायचे आहे का?")) {
                    localStorage.removeItem('access_token');
                    updateAuthUI();
                    authModal.classList.remove('hidden');
                }
            } else {
                authModal.classList.remove('hidden');
            }
        });

        closeAuthModal.addEventListener('click', () => {
            authModal.classList.add('hidden');
        });

        tabLogin.addEventListener('click', () => {
            tabLogin.className = "pb-2 px-3 border-b-2 border-emerald-500 text-emerald-400 font-semibold";
            tabToken.className = "pb-2 px-3 text-slate-400 hover:text-white";
            loginForm.classList.remove('hidden');
            tokenPanel.classList.add('hidden');
        });

        tabToken.addEventListener('click', () => {
            tabToken.className = "pb-2 px-3 border-b-2 border-emerald-500 text-emerald-400 font-semibold";
            tabLogin.className = "pb-2 px-3 text-slate-400 hover:text-white";
            tokenPanel.classList.remove('hidden');
            loginForm.classList.add('hidden');
        });

        // 1. Direct Login API Handler
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            loginError.classList.add('hidden');
            loginSubmitBtn.innerText = "लॉगिन होत आहे...";
            loginSubmitBtn.disabled = true;

            try {
                const res = await fetch('/api/v1/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        email: loginEmail.value.trim(),
                        password: loginPassword.value
                    })
                });

                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    throw new Error(errData.detail || "लॉगिन अयशस्वी. कृपया ईमेल आणि पासवर्ड तपासा.");
                }

                const data = await res.json();
                if (data.access_token) {
                    localStorage.setItem('access_token', data.access_token);
                    updateAuthUI();
                    authModal.classList.add('hidden');
                    statusIndicator.innerText = "🎉 लॉगिन यशस्वी! आता माइक बटण दाबून प्रश्न विचारा.";

                    // If user had asked a question that failed, re-run it automatically!
                    if (pendingQuestion) {
                        const q = pendingQuestion;
                        pendingQuestion = null;
                        processVoiceQuery(q);
                    }
                }
            } catch (err) {
                loginError.innerText = err.message;
                loginError.classList.remove('hidden');
            } finally {
                loginSubmitBtn.innerText = "लॉगिन करा आणि व्हॉईस सुरू करा";
                loginSubmitBtn.disabled = false;
            }
        });

        // 2. Token Paste Handler
        saveTokenBtn.addEventListener('click', () => {
            const raw = tokenInput.value.trim().replace(/^Bearer\s+/i, '');
            if (raw) {
                localStorage.setItem('access_token', raw);
                updateAuthUI();
                authModal.classList.add('hidden');
                statusIndicator.innerText = "✅ टोकन सेव्ह झाले! आता प्रश्न विचारा.";

                if (pendingQuestion) {
                    const q = pendingQuestion;
                    pendingQuestion = null;
                    processVoiceQuery(q);
                }
            } else {
                alert("कृपया वैध टोकन पेस्ट करा.");
            }
        });

        // Speech Recognition Init
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition) {
            recognition = new SpeechRecognition();
            recognition.continuous = false;
            recognition.interimResults = false;

            recognition.onstart = () => {
                isListening = true;
                micBtn.classList.add('mic-active', 'from-red-600', 'to-rose-500');
                audioWaveContainer.classList.remove('hidden');
                statusIndicator.innerText = "🎙️ ऐकत आहे (Listening)... आता बोला!";
                statusIndicator.className = "text-sm font-semibold text-red-400 mb-3 text-center animate-pulse";
            };

            recognition.onresult = (event) => {
                const spokenText = event.results[0][0].transcript;
                statusIndicator.innerText = `तुम्ही विचारले: "${spokenText}"`;
                processVoiceQuery(spokenText);
            };

            recognition.onerror = (event) => {
                resetMicState();
                if (event.error === 'not-allowed') {
                    statusIndicator.innerText = "❌ मायक्रोफोन परवानगी नाकारली. ब्राऊझर सेटिंग्जमध्ये माइक सुरू करा.";
                } else {
                    statusIndicator.innerText = "माइक बटण दाबा आणि पुन्हा बोला.";
                }
            };

            recognition.onend = () => {
                resetMicState();
            };
        } else {
            statusIndicator.innerText = "⚠️ तुमच्या ब्राऊझरमध्ये Web Speech उपलब्ध नाही. कृपया Chrome किंवा Edge वापरा.";
        }

        function resetMicState() {
            isListening = false;
            micBtn.classList.remove('mic-active', 'from-red-600', 'to-rose-500');
            audioWaveContainer.classList.add('hidden');
        }

        // Toggle Mic
        micBtn.addEventListener('click', () => {
            if (synth && synth.speaking) {
                synth.cancel();
                stopAudioBtn.classList.add('hidden');
            }

            if (!recognition) {
                alert("Speech recognition is not supported in this browser. Please use Chrome/Edge.");
                return;
            }

            if (isListening) {
                recognition.stop();
            } else {
                recognition.lang = langSelect.value;
                try {
                    recognition.start();
                } catch (e) {
                    recognition.stop();
                }
            }
        });

        // Toggle Auto-Speak
        toggleSpeakBtn.addEventListener('click', () => {
            autoSpeak = !autoSpeak;
            if (autoSpeak) {
                speakerIcon.innerText = "🔊";
                speakerLabel.innerText = "व्हॉईस चालू (Voice ON)";
                toggleSpeakBtn.className = "flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition bg-emerald-950/60 border-emerald-600/50 text-emerald-300";
            } else {
                speakerIcon.innerText = "🔇";
                speakerLabel.innerText = "व्हॉईस बंद (Muted)";
                toggleSpeakBtn.className = "flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition bg-slate-800 border-slate-700 text-slate-400";
                if (synth && synth.speaking) synth.cancel();
            }
        });

        // Stop Audio Button
        stopAudioBtn.addEventListener('click', () => {
            if (synth) synth.cancel();
            stopAudioBtn.classList.add('hidden');
            statusIndicator.innerText = "आवाज थांबवला.";
        });

        // Text input submit
        textForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const q = textInput.value.trim();
            if (q) {
                textInput.value = "";
                processVoiceQuery(q);
            }
        });

        function askPreset(text) {
            processVoiceQuery(text);
        }

        // Process Query with Retail-OS Backend & Gemini API
        async function processVoiceQuery(questionText) {
            addMessageToChat('user', questionText);
            statusIndicator.innerText = "⚡ जेमिनी दुकानाचा डेटा तपासून उत्तर तयार करत आहे...";
            statusIndicator.className = "text-sm font-semibold text-emerald-400 mb-3 text-center";

            // Prepare Auth Header
            const headers = { 'Content-Type': 'application/json' };
            const token = localStorage.getItem('access_token');
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }

            try {
                const response = await fetch('/api/v1/ai/voice-query', {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({
                        query: questionText,
                        language: langSelect.value
                    })
                });

                if (!response.ok) {
                    if (response.status === 401 || response.status === 403) {
                        pendingQuestion = questionText;
                        updateAuthUI();
                        authModal.classList.remove('hidden');
                        const errMsg = "लॉगिन टोकन आवश्यक आहे. कृपया उघडलेल्या बॉक्समध्ये लॉगिन करा किंवा Swagger UI मधील टोकन पेस्ट करा.";
                        addMessageToChat('bot', errMsg, errMsg);
                        statusIndicator.innerText = "⚠️ लॉगिन आवश्यक आहे (वर दिलेल्या बटणावर क्लिक करा).";
                        return;
                    }
                    throw new Error(`Server returned status: ${response.status}`);
                }

                const data = await response.json();
                statusIndicator.innerText = "✅ उत्तर मिळाले!";
                addMessageToChat('bot', data.answer, data.speech_text, data.suggested_actions);

                // Play Natural Voice via Text-to-Speech (TTS)
                if (autoSpeak && data.speech_text) {
                    speakAnswer(data.speech_text, data.language || langSelect.value);
                }

            } catch (err) {
                console.error("Voice query failed:", err);
                statusIndicator.innerText = "❌ त्रुटी आली. कृपया पुन्हा विचारा.";
                addMessageToChat('bot', "क्षमस्व, उत्तर मिळवण्यात अडचण आली. कृपया पुन्हा विचारा किंवा इंटरनेट कनेक्शन तपासा.");
            }
        }

        // Text-to-Speech Voice Player
        function speakAnswer(cleanSpeechText, langCode) {
            if (!synth) return;
            synth.cancel();

            const utterance = new SpeechSynthesisUtterance(cleanSpeechText);
            utterance.lang = langCode || 'mr-IN';
            utterance.rate = 1.0;
            utterance.pitch = 1.0;

            const voices = synth.getVoices();
            const marathiVoice = voices.find(v => v.lang === 'mr-IN' || v.lang === 'mr' || v.name.toLowerCase().includes('marathi'));
            const indianVoice = voices.find(v => v.lang.includes('IN') || v.name.toLowerCase().includes('india'));
            if (marathiVoice) {
                utterance.voice = marathiVoice;
            } else if (indianVoice) {
                utterance.voice = indianVoice;
            }

            utterance.onstart = () => {
                stopAudioBtn.classList.remove('hidden');
                audioWaveContainer.classList.remove('hidden');
                statusIndicator.innerText = "🔊 असिस्टंट बोलत आहे (Speaking)...";
            };

            utterance.onend = () => {
                stopAudioBtn.classList.add('hidden');
                audioWaveContainer.classList.add('hidden');
                statusIndicator.innerText = "माइक बटण दाबा आणि पुढील प्रश्न विचारा.";
            };

            utterance.onerror = (e) => {
                console.warn("TTS error:", e);
                stopAudioBtn.classList.add('hidden');
                audioWaveContainer.classList.add('hidden');
            };

            synth.speak(utterance);
        }

        // Render Conversation Chat Bubbles
        function addMessageToChat(sender, text, speechText = null, actions = []) {
            const row = document.createElement('div');
            row.className = sender === 'user' 
                ? "flex items-start justify-end gap-3" 
                : "flex items-start gap-3 bg-slate-900/90 border border-slate-800 p-4 rounded-2xl shadow-md";

            const formattedHtml = text
                .replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>')
                .replace(/\\*(.*?)\\*/g, '<em>$1</em>')
                .replace(/\\n/g, '<br>');

            if (sender === 'user') {
                row.innerHTML = `
                    <div class="bg-gradient-to-r from-emerald-600 to-teal-600 text-white px-4 py-2.5 rounded-2xl max-w-lg shadow-md text-sm">
                        <div class="text-[11px] text-emerald-200 mb-0.5">तुम्ही (You)</div>
                        <div>${text}</div>
                    </div>
                    <div class="w-8 h-8 rounded-full bg-emerald-600/30 text-white flex items-center justify-center shrink-0 text-sm">
                        👤
                    </div>
                `;
            } else {
                let actionsHtml = '';
                if (actions && actions.length > 0) {
                    actionsHtml = `
                        <div class="mt-3 pt-2 border-t border-slate-800/80 flex flex-wrap items-center gap-1.5">
                            <span class="text-[11px] text-slate-500 mr-1">शिफारस केलेल्या कृती:</span>
                            ${actions.map(a => `<span class="text-[11px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded border border-slate-700">${a}</span>`).join('')}
                        </div>
                    `;
                }

                let speakBtnHtml = '';
                if (speechText) {
                    speakBtnHtml = `
                        <button onclick="speakAnswer('${speechText.replace(/'/g, "\\'")}', '${langSelect.value}')" class="text-xs flex items-center gap-1 text-emerald-400 hover:text-emerald-300 bg-emerald-950/40 px-2.5 py-1 rounded-md border border-emerald-800/50 transition">
                            🔊 पुन्हा ऐका (Replay Voice)
                        </button>
                    `;
                }

                row.innerHTML = `
                    <div class="w-9 h-9 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center shrink-0">
                        🤖
                    </div>
                    <div class="flex-1">
                        <div class="flex items-center justify-between mb-1">
                            <span class="font-semibold text-sm text-emerald-400">Retail-OS AI Copilot</span>
                            ${speakBtnHtml}
                        </div>
                        <div class="text-sm text-slate-200 leading-relaxed">${formattedHtml}</div>
                        ${actionsHtml}
                    </div>
                `;
            }

            chatHistory.appendChild(row);
            chatHistory.scrollTop = chatHistory.scrollHeight;
        }

        if (synth) {
            synth.onvoiceschanged = () => { synth.getVoices(); };
        }
    </script>
</body>
</html>
"""
