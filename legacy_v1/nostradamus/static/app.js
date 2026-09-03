document.addEventListener('DOMContentLoaded', () => {
    const startBtn = document.getElementById('start-btn');
    const terminal = document.getElementById('terminal-output');
    const jsonOutput = document.getElementById('json-output');
    const logPulse = document.getElementById('log-pulse');
    
    let ws = null;
    let isRunning = false;

    // Conectar WebSocket
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/pipeline`;
        
        ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            appendLog('Sistema', 'INFO', 'Conexión establecida con Nostradamus Core.');
            startBtn.disabled = false;
        };
        
        ws.onclose = () => {
            appendLog('Sistema', 'WARNING', 'Conexión perdida. Reconectando en 3s...');
            startBtn.disabled = true;
            setTimeout(connectWebSocket, 3000);
        };
        
        ws.onerror = (error) => {
            console.error('WebSocket Error:', error);
        };
        
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            handleMessage(data);
        };
    }

    // Manejar mensajes del Backend
    function handleMessage(data) {
        switch(data.type) {
            case 'log':
                appendLog('Pipeline', data.level, data.msg);
                break;
            case 'step':
                updateStep(data.num, data.status);
                break;
            case 'result':
                finishRun();
                if (data.data.error) {
                    appendLog('Sistema', 'ERROR', data.data.error);
                } else {
                    displayJSON(data.data);
                }
                break;
            case 'error':
                finishRun();
                appendLog('Sistema', 'ERROR', `Fatal Error: ${data.msg}`);
                break;
        }
    }

    // Actualizar UI de los pasos
    function updateStep(num, status) {
        const stepEl = document.getElementById(`step-${num}`);
        if (!stepEl) return;
        
        const statusText = stepEl.querySelector('.step-status');
        
        // Reset classes
        stepEl.className = 'step';
        stepEl.classList.add(status);
        
        const statusMap = {
            'pending': 'Pendiente',
            'running': 'Ejecutando...',
            'completed': 'Completado',
            'failed': 'Fallido',
            'skipped': 'Omitido'
        };
        
        statusText.textContent = statusMap[status] || status;
    }

    // Anadir log a la terminal web
    function appendLog(source, level, msg) {
        const isHeader = msg.startsWith('=') || msg.startsWith('---') || msg.startsWith('[*]');
        const cssClass = isHeader ? 'log-HEADER' : `log-${level}`;
        
        const now = new Date();
        const timeStr = now.toTimeString().split(' ')[0];
        
        const line = document.createElement('div');
        line.className = `log-line ${cssClass}`;
        
        line.innerHTML = `<span class="log-time">[${timeStr}]</span> ${escapeHtml(msg)}`;
        
        terminal.appendChild(line);
        terminal.scrollTop = terminal.scrollHeight;
    }

    // Mostrar JSON con syntax highlighting
    function displayJSON(obj) {
        let jsonStr = JSON.stringify(obj, null, 2);
        
        // Basic Syntax Highlighting
        jsonStr = jsonStr.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        jsonStr = jsonStr.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
            let cls = 'json-number';
            if (/^"/.test(match)) {
                if (/:$/.test(match)) {
                    cls = 'json-key';
                } else {
                    cls = 'json-string';
                }
            } else if (/true|false/.test(match)) {
                cls = 'json-boolean';
            } else if (/null/.test(match)) {
                cls = 'json-null';
            }
            return '<span class="' + cls + '">' + match + '</span>';
        });
        
        jsonOutput.innerHTML = jsonStr;
    }

    function escapeHtml(unsafe) {
        return unsafe
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }

    // Boton de Inicio
    startBtn.addEventListener('click', () => {
        if (!ws || ws.readyState !== WebSocket.OPEN || isRunning) return;
        
        isRunning = true;
        startBtn.disabled = true;
        startBtn.querySelector('.btn-text').textContent = 'Ejecutando...';
        logPulse.classList.add('active');
        
        terminal.innerHTML = '';
        jsonOutput.innerHTML = '<span class="placeholder-text">Procesando...</span>';
        
        for (let i = 1; i <= 4; i++) updateStep(i, 'pending');
        
        ws.send('start');
    });

    function finishRun() {
        isRunning = false;
        startBtn.disabled = false;
        startBtn.querySelector('.btn-text').textContent = 'Iniciar Simulación';
        logPulse.classList.remove('active');
    }

    // Iniciar conexion
    connectWebSocket();
});
