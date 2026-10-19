document.addEventListener('DOMContentLoaded', () => {
    // API endpoint base URL
    const API_URL = new URL('/api/v1/agent/query', window.location.origin).href;

    // DOM Elements
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const collapseSidebarBtn = document.getElementById('collapse-sidebar-btn');
    const newChatBtn = document.getElementById('new-chat-btn');
    const sessionsList = document.getElementById('sessions-list');
    const chatTitle = document.getElementById('chat-title');
    const chatMessages = document.getElementById('chat-messages');
    const welcomeScreen = document.getElementById('welcome-screen');
    const chatInputForm = document.getElementById('chat-input-form');
    const chatTextarea = document.getElementById('chat-textarea');
    const quickPromptBtns = document.querySelectorAll('.quick-prompt-btn');
    const thinkToggleBtn = document.getElementById('think-toggle-btn');

    // State Variables
    let sessions = JSON.parse(localStorage.getItem('agrimitra_sessions')) || [];
    let currentSessionId = localStorage.getItem('agrimitra_current_session_id') || null;
    let thinkModeActive = false;
    let messageInFlight = false;

    // Helper: Generate unique ID
    const generateId = () => 'session_' + Math.random().toString(36).substring(2, 9);

    // Initializing
    init();

    function init() {
        renderSessionsList();
        if (currentSessionId && getSessionById(currentSessionId)) {
            loadSession(currentSessionId);
        } else {
            startNewSession();
        }
        setupEventListeners();
    }

    function setupEventListeners() {
        // Sidebar Mobile Toggle / Restore Collapsed Sidebar
        sidebarToggle.addEventListener('click', () => {
            if (window.innerWidth <= 900) {
                sidebar.classList.toggle('open');
            } else {
                sidebar.classList.toggle('collapsed');
            }
        });

        // Collapse Sidebar button (inside sidebar)
        if (collapseSidebarBtn) {
            collapseSidebarBtn.addEventListener('click', () => {
                sidebar.classList.add('collapsed');
            });
        }

        // Click outside mobile sidebar to close it
        document.addEventListener('click', (e) => {
            if (window.innerWidth <= 900 && 
                sidebar.classList.contains('open') && 
                !sidebar.contains(e.target) && 
                !sidebarToggle.contains(e.target)) {
                sidebar.classList.remove('open');
            }
        });

        // New Chat Button
        newChatBtn.addEventListener('click', () => {
            startNewSession();
            if (window.innerWidth <= 900) {
                sidebar.classList.remove('open');
            }
        });

        // Textarea Auto-growth
        chatTextarea.addEventListener('input', () => {
            chatTextarea.style.height = 'auto';
            chatTextarea.style.height = (chatTextarea.scrollHeight) + 'px';
        });

        // Textarea submit on enter key (without shift)
        chatTextarea.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                chatInputForm.dispatchEvent(new Event('submit'));
            }
        });

        // Submit Form
        chatInputForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const text = chatTextarea.value.trim();
            if (!text) return;
            sendMessage(text);
        });

        // Quick Prompt Buttons
        quickPromptBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const prompt = btn.getAttribute('data-prompt');
                if (prompt) {
                    sendMessage(prompt);
                }
            });
        });

        // Deep Think Toggle
        if (thinkToggleBtn) {
            thinkToggleBtn.addEventListener('click', () => {
                thinkModeActive = !thinkModeActive;
                thinkToggleBtn.classList.toggle('active', thinkModeActive);
            });
        }

    }

    // --- Session CRUD functions ---

    function getSessionById(id) {
        return sessions.find(s => s.id === id);
    }

    function startNewSession() {
        const newId = generateId();
        const newSession = {
            id: newId,
            title: 'New Chat',
            messages: [],
            timestamp: Date.now()
        };
        sessions.unshift(newSession);
        currentSessionId = newId;
        saveSessions();
        renderSessionsList();
        loadSession(newId);
    }

    function loadSession(id) {
        currentSessionId = id;
        localStorage.setItem('agrimitra_current_session_id', id);
        
        const session = getSessionById(id);
        if (!session) return;

        if (chatTitle) {
            chatTitle.textContent = session.title;
        }
        renderMessages(session.messages);

        // Highlight active session
        document.querySelectorAll('.session-item').forEach(item => {
            item.classList.toggle('active', item.getAttribute('data-id') === id);
        });
    }

    function deleteSession(id, event) {
        if (event) event.stopPropagation();
        
        sessions = sessions.filter(s => s.id !== id);
        saveSessions();
        renderSessionsList();

        if (currentSessionId === id) {
            if (sessions.length > 0) {
                loadSession(sessions[0].id);
            } else {
                startNewSession();
            }
        }
    }

    function saveSessions() {
        localStorage.setItem('agrimitra_sessions', JSON.stringify(sessions));
    }

    // Render left sidebar sessions
    function renderSessionsList() {
        sessionsList.innerHTML = '';
        if (sessions.length === 0) {
            sessionsList.innerHTML = '<div style="padding: 1rem 1.4rem; font-size: 0.8rem; color: var(--text-secondary); opacity: 0.5;">No history</div>';
            return;
        }

        sessions.forEach(session => {
            const item = document.createElement('div');
            item.className = `session-item ${session.id === currentSessionId ? 'active' : ''}`;
            item.setAttribute('data-id', session.id);
            
            // Generate title based on first user message if default
            let displayTitle = session.title;
            if (displayTitle.length > 22) {
                displayTitle = displayTitle.substring(0, 20) + '...';
            }

            item.innerHTML = `
                <div class="session-info">
                    <span class="session-icon">💬</span>
                    <span class="session-title" title="${session.title}">${displayTitle}</span>
                </div>
                <button class="delete-session-btn" title="Delete chat">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="3 6 5 6 21 6"></polyline>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                    </svg>
                </button>
            `;

            item.addEventListener('click', () => loadSession(session.id));
            item.querySelector('.delete-session-btn').addEventListener('click', (e) => deleteSession(session.id, e));

            sessionsList.appendChild(item);
        });
    }

    // --- Message Rendering & sending ---

    function renderMessages(messages) {
        // Clear message stream
        chatMessages.innerHTML = '';
        chatMessages.appendChild(welcomeScreen);

        if (messages.length === 0) {
            welcomeScreen.style.display = 'flex';
        } else {
            welcomeScreen.style.display = 'none';
            messages.forEach(msg => {
                appendMessageBubble(msg.role, msg.content);
            });
        }
        scrollToBottom();
    }

    function appendMessageBubble(role, content) {
        welcomeScreen.style.display = 'none';
        
        const row = document.createElement('div');
        row.className = `message-row ${role}`;

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';
        
        if (role === 'bot') {
            bubble.innerHTML = formatMarkdown(content);
        } else {
            // Check if user message had think mode active (we can style it if needed)
            bubble.textContent = content;
        }

        row.appendChild(bubble);
        chatMessages.appendChild(row);
        scrollToBottom();
    }

    function formatMarkdown(text) {
        const escapeHtml = value => value
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
        const inline = value => escapeHtml(value)
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/(^|[^*])\*([^*]+)\*(?!\*)/g, '$1<em>$2</em>');
        const lines = text.replace(/\r\n?/g, '\n').split('\n');
        const output = [];
        let listType = null;
        let inTable = false;

        const closeList = () => {
            if (listType) {
                output.push(`</${listType}>`);
                listType = null;
            }
        };
        const closeTable = () => {
            if (inTable) {
                output.push('</tbody></table></div>');
                inTable = false;
            }
        };
        const tableCells = line => line.trim().replace(/^\||\|$/g, '')
            .split('|').map(cell => cell.trim());
        const isTableDivider = line =>
            /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(line.trim());

        for (let index = 0; index < lines.length; index += 1) {
            const line = lines[index].trim();
            if (!line) {
                closeList();
                closeTable();
                continue;
            }

            const heading = line.match(/^(#{1,4})\s+(.+)$/);
            if (heading) {
                closeList();
                closeTable();
                const level = Math.min(heading[1].length + 1, 6);
                output.push(`<h${level}>${inline(heading[2])}</h${level}>`);
                continue;
            }

            if (line.includes('|') && index + 1 < lines.length && isTableDivider(lines[index + 1])) {
                closeList();
                closeTable();
                const headers = tableCells(line).map(cell => `<th>${inline(cell)}</th>`).join('');
                output.push(`<div class="message-table-wrap"><table><thead><tr>${headers}</tr></thead><tbody>`);
                inTable = true;
                index += 1;
                continue;
            }

            if (inTable && line.includes('|')) {
                const cells = tableCells(line).map(cell => `<td>${inline(cell)}</td>`).join('');
                output.push(`<tr>${cells}</tr>`);
                continue;
            }
            closeTable();

            const listMatch = line.match(/^([-*]|\d+\.)\s+(.+)$/);
            if (listMatch) {
                const nextListType = /^\d/.test(listMatch[1]) ? 'ol' : 'ul';
                if (listType !== nextListType) {
                    closeList();
                    output.push(`<${nextListType}>`);
                    listType = nextListType;
                }
                output.push(`<li>${inline(listMatch[2])}</li>`);
                continue;
            }

            closeList();
            output.push(`<p>${inline(line)}</p>`);
        }

        closeList();
        closeTable();
        return output.join('');
    }

    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Send user message
    async function sendMessage(text) {
        if (messageInFlight) return;
        chatTextarea.value = '';
        chatTextarea.style.height = 'auto';

        const session = getSessionById(currentSessionId);
        if (!session) return;
        messageInFlight = true;

        // Set session title to the first user query if it's default
        if (session.messages.length === 0) {
            session.title = text.length > 24 ? text.substring(0, 22) + '...' : text;
            if (chatTitle) {
                chatTitle.textContent = session.title;
            }
            renderSessionsList();
        }

        const history = session.messages.slice(-20).map(message => ({
            role: message.role === 'bot' ? 'assistant' : 'user',
            content: message.content.replace(/^\[Deep Think Mode\]\s*/, '')
        }));
        session.messages.push({ role: 'user', content: text });
        saveSessions();

        appendMessageBubble('user', text);

        // Show typing indicator
        const typingIndicator = appendTypingIndicator();
        scrollToBottom();
        const controller = new AbortController();
        const requestTimeout = window.setTimeout(() => controller.abort(), 70000);

        try {
            const response = await fetch(API_URL, {
                method: 'POST',
                signal: controller.signal,
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    query: text,
                    history,
                    detailed: thinkModeActive,
                    language: window.AgriMitraI18n?.getLanguage() || 'en'
                })
            });

            if (!response.ok) {
                // Try to get error detail from server response
                let detail = '';
                try {
                    const errData = await response.json();
                    detail = errData.detail || '';
                } catch (_) {}
                throw new Error(detail || `Server error: ${response.status}`);
            }

            const data = await response.json();
            if (typeof data.response !== 'string' || !data.response.trim()) {
                throw new Error('The AI service returned an empty response. Please retry.');
            }
            const botReply = data.response;

            // Remove typing indicator
            typingIndicator.remove();

            // Add bot message to state
            session.messages.push({ role: 'bot', content: botReply });
            saveSessions();

            // Render bot bubble
            appendMessageBubble('bot', botReply);

        } catch (error) {
            console.error('Error querying backend:', error);
            typingIndicator.remove();
            const detail = error.name === 'AbortError'
                ? 'The request took too long. Please retry in a moment.'
                : error.message || 'AgriMitra could not complete this request.';
            const errorMsg = `⚠️ ${detail.slice(0, 500)}`;

            session.messages.push({ role: 'bot', content: errorMsg });
            saveSessions();
            appendMessageBubble('bot', errorMsg);
        } finally {
            window.clearTimeout(requestTimeout);
            messageInFlight = false;
        }
    }

    function appendTypingIndicator() {
        const row = document.createElement('div');
        row.className = 'message-row bot typing-row';

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';

        bubble.innerHTML = `
            <div class="typing-indicator">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        `;

        row.appendChild(bubble);
        chatMessages.appendChild(row);
        return row;
    }
});
