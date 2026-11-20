def get_customer_support_widget_html() -> str:
    return """<!DOCTYPE html>
<html lang="mr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Retail-OS | 24/7 AI Customer Support & Returns Bot</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+Devanagari:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body {
            font-family: 'Noto Sans Devanagari', 'Inter', sans-serif;
            background: #0b1329;
        }
        .chat-bubble-bot {
            background: #1e293b;
            border-left: 3px solid #10b981;
        }
        .chat-bubble-user {
            background: #0284c7;
        }
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: #0f172a; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
        .no-scrollbar::-webkit-scrollbar { display: none; }
        .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
    </style>
</head>
<body class="min-h-screen flex flex-col items-center justify-center p-2 sm:p-4 text-slate-100">

    <div class="w-full max-w-2xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl flex flex-col h-[92vh] overflow-hidden">
        
        <!-- Widget Header -->
        <header class="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 border-b border-slate-800 p-3.5 flex items-center justify-between gap-2">
            <div class="flex items-center gap-3">
                <div class="relative">
                    <div class="w-10 h-10 rounded-xl bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 font-bold text-lg">
                        🤖
                    </div>
                    <span class="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-emerald-500 border-2 border-slate-900 rounded-full animate-pulse"></span>
                </div>
                <div>
                    <h1 class="text-sm sm:text-base font-bold text-white flex items-center gap-2">
                        Retail-OS AI Customer Care
                        <span class="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">24/7 Active</span>
                        <span id="storeBadge" class="hidden text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 flex items-center gap-1">📍 <span id="storeBadgeName"></span></span>
                    </h1>
                    <p class="text-xs text-slate-400">ऑर्डर ट्रॅकिंग • बिल डाऊनलोड • रिटर्न व तक्रार निवारण</p>
                </div>
            </div>

            <!-- Audio Toggle Button -->
            <div class="flex items-center gap-2">
                <button id="voiceToggleBtn" class="px-2.5 py-1 text-xs rounded-lg border border-slate-700 bg-slate-800 text-slate-300 hover:text-white transition flex items-center gap-1 shadow-sm">
                    🔊 <span id="voiceStatus">Audio ON</span>
                </button>
            </div>
        </header>

        <!-- Quick Action Suggestion Pills (10 Questions) -->
        <div class="bg-slate-950/80 border-b border-slate-800/80 px-3 py-2 flex items-center gap-2 overflow-x-auto text-xs no-scrollbar">
            <button onclick="sendQuickQuery('माझी ऑर्डर कुठे आहे?')" class="whitespace-nowrap px-3 py-1.5 rounded-full bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 hover:text-white transition flex items-center gap-1.5 shadow-sm">
                📦 ऑर्डर ट्रॅक करा
            </button>
            <button onclick="sendQuickQuery('मला टॅक्स इनव्हॉइस बिल डाऊनलोड करायचे आहे')" class="whitespace-nowrap px-3 py-1.5 rounded-full bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 hover:text-white transition flex items-center gap-1.5 shadow-sm">
                🧾 जीएसटी बिल डाऊनलोड
            </button>
            <button onclick="sendQuickQuery('वस्तू रिटर्न किंवा बदलून हवी आहे')" class="whitespace-nowrap px-3 py-1.5 rounded-full bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 hover:text-white transition flex items-center gap-1.5 shadow-sm">
                🔄 वस्तू रिटर्न व रिफंड
            </button>
            <button onclick="sendQuickQuery('दुकान कधी उघडे असते आणि पत्ता काय?')" class="whitespace-nowrap px-3 py-1.5 rounded-full bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 hover:text-white transition flex items-center gap-1.5 shadow-sm">
                🏪 दुकान वेळ व पत्ता
            </button>
            <button onclick="sendQuickQuery('तुमच्या सर्व शाखांची यादी दाखवा')" class="whitespace-nowrap px-3 py-1.5 rounded-full bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 hover:text-white transition flex items-center gap-1.5 shadow-sm">
                🏢 सर्व शाखांची माहिती
            </button>
            <button onclick="sendQuickQuery('होम डिलिव्हरी कधी आणि कशी मिळते?')" class="whitespace-nowrap px-3 py-1.5 rounded-full bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 hover:text-white transition flex items-center gap-1.5 shadow-sm">
                🛵 घरपोच डिलिव्हरी माहिती
            </button>
            <button onclick="sendQuickQuery('WhatsApp वरून किराणा ऑर्डर कशी करायची?')" class="whitespace-nowrap px-3 py-1.5 rounded-full bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 hover:text-white transition flex items-center gap-1.5 shadow-sm">
                💬 WhatsApp ऑर्डर कशी करावी?
            </button>
            <button onclick="sendQuickQuery('पेमेंटचे कोणते पर्याय उपलब्ध आहेत?')" class="whitespace-nowrap px-3 py-1.5 rounded-full bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 hover:text-white transition flex items-center gap-1.5 shadow-sm">
                💳 पेमेंट पर्याय (UPI/Cash/Khata)
            </button>
            <button onclick="sendQuickQuery('आजच्या चालू ऑफर्स आणि डिस्काउंट्स सांगा')" class="whitespace-nowrap px-3 py-1.5 rounded-full bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 hover:text-white transition flex items-center gap-1.5 shadow-sm">
                🎁 आजच्या ऑफर्स व सवलती
            </button>
            <button onclick="sendQuickQuery('थेट स्टोअर मॅनेजरशी संपर्क कसा करायचा?')" class="whitespace-nowrap px-3 py-1.5 rounded-full bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 hover:text-white transition flex items-center gap-1.5 shadow-sm">
                📞 मॅनेजरशी बोला (हेल्पलाईन)
            </button>
        </div>

        <!-- Message Flow Area -->
        <main id="chatBox" class="flex-1 p-4 overflow-y-auto space-y-4">
            
            <!-- Bot Initial Message -->
            <div class="flex items-start gap-3">
                <div class="w-8 h-8 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-sm font-bold flex-shrink-0">
                    🤖
                </div>
                <div class="chat-bubble-bot p-3.5 rounded-2xl rounded-tl-none max-w-[85%] text-sm text-slate-200 leading-relaxed shadow-sm">
                    <p class="font-semibold text-emerald-400 mb-1">सस्नेह नमस्कार! 🙏</p>
                    <p>मी आपला २४/७ AI ग्राहक सेवा प्रतिनिधी आहे. मी तुम्हाला पुढील सेवांमध्ये मदत करू शकतो:</p>
                    <ul class="list-disc pl-5 my-2 space-y-1 text-slate-300 text-xs">
                        <li><strong>ऑर्डर ट्रॅकिंग:</strong> ऑर्डर नंबर सांगा आणि थेट डिलिव्हरी स्थिती पाहा.</li>
                        <li><strong>बिल डाऊनलोड:</strong> एका क्लिकवर आपले अधिकृत Tax Invoice PDF मिळवा.</li>
                        <li><strong>रिटर्न व एक्सचेंज:</strong> १४ दिवसांच्या आत सोप्या पद्धतीने रिटर्न नोंदवा.</li>
                        <li><strong>दुकान माहिती:</strong> कामाचे तास, पत्ता आणि संपर्क नंबर.</li>
                    </ul>
                    <p class="text-xs text-slate-400 mt-2">खाली आपला प्रश्न टाईप करा किंवा वरील पर्यायांवर क्लिक करा!</p>
                </div>
            </div>

        </main>

        <!-- Typing Indicator -->
        <div id="typingIndicator" class="hidden px-6 py-2 text-xs text-slate-400 flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-bounce"></span>
            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-bounce" style="animation-delay: 0.2s"></span>
            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-bounce" style="animation-delay: 0.4s"></span>
            <span>AI उत्तर शोधत आहे...</span>
        </div>

        <!-- Chat Input Form -->
        <footer class="p-3 bg-slate-950 border-t border-slate-800 flex flex-col gap-2">
            <form id="chatForm" class="flex items-center gap-2">
                <input 
                    type="text" 
                    id="phoneInput" 
                    placeholder="फोन (पर्यायी)" 
                    class="w-28 sm:w-32 bg-slate-900 border border-slate-700 text-xs px-2.5 py-2.5 rounded-xl text-slate-200 focus:outline-none focus:border-indigo-500"
                />
                <input 
                    type="text" 
                    id="messageInput" 
                    placeholder="येथे प्रश्न विचारा (उदा. ORD-1001 कुठे आहे?)..." 
                    autocomplete="off"
                    class="flex-1 bg-slate-900 border border-slate-700 text-xs sm:text-sm px-3.5 py-2.5 rounded-xl text-slate-200 focus:outline-none focus:border-emerald-500"
                />
                <button 
                    type="submit" 
                    class="bg-emerald-600 hover:bg-emerald-500 text-white font-medium px-4 py-2.5 rounded-xl text-xs sm:text-sm flex items-center gap-1.5 transition shadow-lg shadow-emerald-900/20 flex-shrink-0"
                >
                    <span>पाठवा</span>
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"></path>
                    </svg>
                </button>
            </form>
            <div class="flex items-center justify-between text-[11px] text-slate-500 px-1">
                <span>⚡ Powered by Retail-OS AI Support Engine & Gemini 1.5</span>
                <span>🔒 सुरक्षित व थेट दुकानाशी कनेक्टेड</span>
            </div>
        </footer>

    </div>

    <script>
        const chatBox = document.getElementById('chatBox');
        const chatForm = document.getElementById('chatForm');
        const messageInput = document.getElementById('messageInput');
        const phoneInput = document.getElementById('phoneInput');
        const typingIndicator = document.getElementById('typingIndicator');
        const voiceToggleBtn = document.getElementById('voiceToggleBtn');
        const voiceStatus = document.getElementById('voiceStatus');

        let isVoiceEnabled = true;

        // Auto-fill phone & store context from URL params or sessionStorage
        const urlParams = new URLSearchParams(window.location.search);
        const prePhone = urlParams.get('phone');
        if (prePhone) {
            phoneInput.value = prePhone;
        }

        let activeStoreId = urlParams.get('store_id') || sessionStorage.getItem('retailos_store_id');
        let activeTenantId = urlParams.get('tenant_id') || sessionStorage.getItem('retailos_tenant_id');
        let activeStoreName = sessionStorage.getItem('retailos_store_name');

        function updateStoreBadge(name) {
            if (!name) return;
            const badge = document.getElementById('storeBadge');
            const badgeName = document.getElementById('storeBadgeName');
            if (badge && badgeName) {
                badgeName.innerText = name;
                badge.classList.remove('hidden');
            }
        }

        if (activeStoreName) {
            updateStoreBadge(activeStoreName);
        }

        voiceToggleBtn.addEventListener('click', () => {
            isVoiceEnabled = !isVoiceEnabled;
            voiceStatus.innerText = isVoiceEnabled ? "Audio ON" : "Audio OFF";
            voiceToggleBtn.classList.toggle('border-emerald-500', isVoiceEnabled);
            if (!isVoiceEnabled) {
                window.speechSynthesis.cancel();
            }
        });

        function appendUserMessage(text) {
            const wrap = document.createElement('div');
            wrap.className = 'flex justify-end';
            wrap.innerHTML = `
                <div class="chat-bubble-user p-3.5 rounded-2xl rounded-tr-none max-w-[85%] text-sm text-white leading-relaxed shadow">
                    ${escapeHtml(text)}
                </div>
            `;
            chatBox.appendChild(wrap);
            chatBox.scrollTop = chatBox.scrollHeight;
        }

        function appendBotMessage(data) {
            const wrap = document.createElement('div');
            wrap.className = 'flex items-start gap-3';
            
            // Format basic markdown bolding & links
            let formattedReply = formatMarkdown(data.reply || '');

            let actionsHtml = '';
            if (data.suggested_actions && data.suggested_actions.length > 0) {
                actionsHtml = `
                    <div class="mt-3 pt-2 border-t border-slate-700/60 flex flex-wrap gap-1.5">
                        ${data.suggested_actions.map(act => `
                            <button onclick="sendQuickQuery('${escapeHtml(act)}')" class="text-[11px] px-2.5 py-1 rounded-md bg-slate-700 hover:bg-slate-600 text-slate-200 transition">
                                👉 ${escapeHtml(act)}
                            </button>
                        `).join('')}
                    </div>
                `;
            }

            wrap.innerHTML = `
                <div class="w-8 h-8 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-sm font-bold flex-shrink-0">
                    🤖
                </div>
                <div class="chat-bubble-bot p-3.5 rounded-2xl rounded-tl-none max-w-[85%] text-sm text-slate-200 leading-relaxed shadow-sm">
                    <div>${formattedReply}</div>
                    ${actionsHtml}
                </div>
            `;
            chatBox.appendChild(wrap);
            chatBox.scrollTop = chatBox.scrollHeight;

            // Text-to-Speech if enabled
            if (isVoiceEnabled && (data.speech_text || data.reply)) {
                speakAloud(data.speech_text || data.reply);
            }
        }

        async function handleSend(text) {
            if (!text || !text.trim()) return;
            const query = text.trim();
            const phone = phoneInput.value.trim();

            appendUserMessage(query);
            typingIndicator.classList.remove('hidden');
            chatBox.scrollTop = chatBox.scrollHeight;

            try {
                const res = await fetch('/api/v1/support/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        query: query,
                        customer_phone: phone || null,
                        store_id: activeStoreId ? parseInt(activeStoreId) : null,
                        tenant_id: activeTenantId ? parseInt(activeTenantId) : null,
                        language: 'mr'
                    })
                });

                const data = await res.json();
                typingIndicator.classList.add('hidden');

                if (data.data) {
                    if (data.data.store_id) {
                        activeStoreId = data.data.store_id;
                        sessionStorage.setItem('retailos_store_id', activeStoreId);
                    }
                    if (data.data.tenant_id) {
                        activeTenantId = data.data.tenant_id;
                        sessionStorage.setItem('retailos_tenant_id', activeTenantId);
                    }
                    if (data.data.store_name) {
                        activeStoreName = data.data.store_name;
                        sessionStorage.setItem('retailos_store_name', activeStoreName);
                        updateStoreBadge(activeStoreName);
                    }
                }

                appendBotMessage(data);
            } catch (err) {
                typingIndicator.classList.add('hidden');
                appendBotMessage({
                    reply: '⚠️ सर्व्हरशी संपर्क करताना अडचण आली. कृपया पुन्हा प्रयत्न करा किंवा थेट दुकानाशी संपर्क साधा.',
                    suggested_actions: ['Retry', 'Store Information']
                });
            }
        }

        chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const val = messageInput.value;
            messageInput.value = '';
            handleSend(val);
        });

        function sendQuickQuery(str) {
            handleSend(str);
        }

        function speakAloud(text) {
            if (!('speechSynthesis' in window)) return;
            window.speechSynthesis.cancel();
            
            // Clean markdown tokens for clear speech
            const cleanText = text.replace(/[*_#`\\[\\]()]/g, ' ').replace(/https?:\\/\\/\\S+/g, ' ');
            const utterance = new SpeechSynthesisUtterance(cleanText);
            
            // Prefer Marathi/Hindi voice if available
            const voices = window.speechSynthesis.getVoices();
            const marathiVoice = voices.find(v => v.lang.startsWith('mr') || v.lang.startsWith('hi'));
            if (marathiVoice) {
                utterance.voice = marathiVoice;
            }
            utterance.rate = 1.0;
            window.speechSynthesis.speak(utterance);
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function formatMarkdown(text) {
            return text
                .replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>')
                .replace(/\\*(.*?)\\*/g, '<em>$1</em>')
                .replace(/`([^`]+)`/g, '<code class="bg-slate-800 px-1.5 py-0.5 rounded text-amber-300 font-mono text-xs">$1</code>')
                .replace(/\\[([^\\]]+)\\]\\(([^\\)]+)\\)/g, '<a href="$2" target="_blank" class="text-emerald-400 underline font-semibold hover:text-emerald-300">$1 ↗</a>')
                .replace(/\\n/g, '<br/>');
        }
    </script>
</body>
</html>
"""
