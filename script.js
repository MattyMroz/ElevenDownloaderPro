// ==UserScript==
// @name         Eleven Downloader Pro
// @namespace    http://tampermonkey.net/
// @version      1.0
// @description  Professional UI for the advanced audio grabber.
// @author       Hacker
// @match        https://elevenreader.io/*
// @match        https://elevenlabs.io/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

(function () {
    'use strict';

    let audioChunks = [];
    let totalBytes = 0;
    let isRecording = false;
    let isPassive = true;
    let autoDownloadTimer = null;
    let autoDownloadTimeout = 60000;
    const GB_LIMIT = 1024 * 1024 * 1024;

    // --- CORE LOGIC (UNCHANGED) ---
    const hijackAudio = (Ctx) => {
        const originalCreate = Ctx.prototype.createBufferSource;
        Ctx.prototype.createBufferSource = function () {
            const src = originalCreate.call(this);
            const origStart = src.start;
            src.start = function () {
                if (!isPassive) {
                    try {
                        src.playbackRate.value = 16.0;
                    } catch (e) {}
                }
                return origStart.apply(this, arguments);
            };
            return src;
        };
    };
    if (window.AudioContext) hijackAudio(window.AudioContext);
    if (window.webkitAudioContext) hijackAudio(window.webkitAudioContext);

    const OriginalWebSocket = window.WebSocket;
    window.WebSocket = function (url, protocols) {
        const ws = new OriginalWebSocket(url, protocols);
        ws.addEventListener('message', function (event) {
            if (isPassive || !isRecording) return;
            try {
                const data = JSON.parse(event.data);
                if (data && data.audio) {
                    const binaryString = window.atob(data.audio);
                    const len = binaryString.length;
                    const bytes = new Uint8Array(len);
                    for (let i = 0; i < len; i++) {
                        bytes[i] = binaryString.charCodeAt(i);
                    }
                    audioChunks.push(bytes);
                    totalBytes += len;
                    updateUI();
                    resetAutoDownloadTimer();
                    if (totalBytes >= GB_LIMIT) downloadAndClear(true);
                }
            } catch (e) {}
        });
        return ws;
    };
    window.WebSocket.prototype = OriginalWebSocket.prototype;
    Object.assign(window.WebSocket, OriginalWebSocket);

    // --- STYLESHEET INJECTION ---
    function injectStyles() {
        const style = document.createElement('style');
        style.textContent = `
            #er-downloader-panel button {
                padding: 10px; border: none; border-radius: 8px;
                color: #fff; font-weight: 600;
                cursor: pointer; font-size: 12px; transition: all 0.2s;
            }
            #er-downloader-panel button:hover { filter: brightness(1.2); }
            .er-btn-primary { background: #e94560; }
            .er-btn-secondary { background: #2c3e50; }
            .er-btn-action { background: #9370db; }
            .er-btn-paused { background: #f57c00; }
            .er-btn-resume { background: #4caf50; }

            /* Custom Slider Styles */
            input[type=range].er-slider {
                -webkit-appearance: none; width: 100%; background: transparent;
            }
            input[type=range].er-slider::-webkit-slider-runnable-track {
                width: 100%; height: 6px; cursor: pointer;
                background: #2c3e50; border-radius: 3px;
            }
            input[type=range].er-slider::-webkit-slider-thumb {
                -webkit-appearance: none; height: 16px; width: 16px;
                border-radius: 50%; background: #9370db; cursor: pointer;
                margin-top: -5px; box-shadow: 0 0 5px #9370db;
            }
            input[type=range].er-slider::-moz-range-track {
                width: 100%; height: 6px; cursor: pointer;
                background: #2c3e50; border-radius: 3px;
            }
            input[type=range].er-slider::-moz-range-thumb {
                height: 16px; width: 16px; border-radius: 50%;
                background: #9370db; cursor: pointer; border: none;
            }
        `;
        document.head.appendChild(style);
    }

    // --- UI CONSTRUCTION ---
    function createUI() {
        const container = document.createElement('div');
        container.id = 'er-downloader-panel';
        container.style.cssText = `
            position: fixed; top: 20px; right: 20px; width: 280px;
            background: #1a1a2e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif;
            border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,0.6);
            z-index: 9999999; border: 1px solid #4a4a7f; overflow: hidden;
            display: flex; flex-direction: column;
        `;

        const header = document.createElement('div');
        header.style.cssText = `
            background: #16213e; padding: 12px; cursor: move;
            font-weight: 700; font-size: 14px; letter-spacing: 1px;
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: 1px solid #4a4a7f; color: #fff;
        `;
        header.innerHTML = '<span>ELEVEN DOWNLOADER</span><span id="er-online-indicator" style="font-size:10px; color:#9370db;">● PASSIVE</span>';

        const content = document.createElement('div');
        content.style.padding = '15px';

        const statusBox = document.createElement('div');
        statusBox.style.cssText = `
            background: #0f0c29; border-radius: 8px; padding: 10px;
            margin-bottom: 15px; text-align: center; border: 1px solid #4a4a7f;
        `;
        const sizeDisplay = document.createElement('div');
        sizeDisplay.id = 'er-size';
        sizeDisplay.innerText = '0.00 KB';
        sizeDisplay.style.cssText = 'font-size: 24px; font-weight: bold; color: #9370db;';

        const stateDisplay = document.createElement('div');
        stateDisplay.id = 'er-state';
        stateDisplay.innerText = 'PASSIVE MODE';
        stateDisplay.style.cssText = 'font-size: 10px; color: #888; margin-top: 4px; text-transform: uppercase;';

        statusBox.appendChild(sizeDisplay);
        statusBox.appendChild(stateDisplay);

        const btnGrid = document.createElement('div');
        btnGrid.style.cssText = 'display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;';

        const createBtn = (id, text, className) => {
            const btn = document.createElement('button');
            btn.id = id;
            btn.innerText = text;
            btn.className = className;
            return btn;
        };

        const btnRecPause = createBtn('er-rec-pause', 'RECORD', 'er-btn-primary');
        const btnPassive = createBtn('er-passive', 'PASSIVE MODE', 'er-btn-secondary');
        const btnClear = createBtn('er-clear', 'CLEAR RAM', 'er-btn-secondary');
        const btnDownload = createBtn('er-download', 'DOWNLOAD', 'er-btn-action');

        btnRecPause.onclick = () => toggleRecording();
        btnPassive.onclick = () => setMode('PASSIVE');
        btnClear.onclick = () => clearRam();
        btnDownload.onclick = () => downloadAndClear(false);

        btnGrid.appendChild(btnRecPause);
        btnGrid.appendChild(btnPassive);
        btnGrid.appendChild(btnClear);
        btnGrid.appendChild(btnDownload);

        const sliderContainer = document.createElement('div');
        sliderContainer.style.cssText = 'margin-top: 15px;';
        const sliderLabel = document.createElement('label');
        sliderLabel.id = 'er-slider-label';
        sliderLabel.innerText = 'Auto-Download after 60s of silence';
        sliderLabel.style.cssText = 'display: block; font-size: 11px; margin-bottom: 5px; color: #aaa;';
        const slider = document.createElement('input');
        slider.type = 'range';
        slider.min = '10';
        slider.max = '300';
        slider.value = '60';
        slider.className = 'er-slider';
        slider.oninput = (e) => {
            autoDownloadTimeout = parseInt(e.target.value) * 1000;
            sliderLabel.innerText = `Auto-Download after ${e.target.value}s of silence`;
            resetAutoDownloadTimer();
        };

        sliderContainer.appendChild(sliderLabel);
        sliderContainer.appendChild(slider);

        content.appendChild(statusBox);
        content.appendChild(btnGrid);
        content.appendChild(sliderContainer);

        container.appendChild(header);
        container.appendChild(content);
        document.body.appendChild(container);

        let isDragging = false,
            offsetX, offsetY;
        header.onmousedown = (e) => {
            isDragging = true;
            offsetX = e.clientX - container.getBoundingClientRect().left;
            offsetY = e.clientY - container.getBoundingClientRect().top;
        };
        document.onmousemove = (e) => {
            if (isDragging) {
                container.style.left = (e.clientX - offsetX) + 'px';
                container.style.top = (e.clientY - offsetY) + 'px';
                container.style.right = 'auto';
            }
        };
        document.onmouseup = () => isDragging = false;
    }

    // --- LOGIC ---
    function formatSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        else if (bytes < 1048576) return (bytes / 1024).toFixed(2) + ' KB';
        else return (bytes / 1048576).toFixed(2) + ' MB';
    }

    function updateUI() {
        const sizeEl = document.getElementById('er-size');
        const stateEl = document.getElementById('er-state');
        const recPauseBtn = document.getElementById('er-rec-pause');
        const onlineIndicator = document.getElementById('er-online-indicator');

        if (sizeEl) sizeEl.innerText = formatSize(totalBytes);
        if (stateEl) {
            if (isPassive) {
                stateEl.innerText = 'PASSIVE MODE (1.0x)';
                stateEl.style.color = '#888';
                recPauseBtn.innerText = 'RECORD';
                recPauseBtn.className = 'er-btn-primary';
                onlineIndicator.style.color = '#9370db';
                onlineIndicator.innerText = '● PASSIVE';
            } else if (isRecording) {
                stateEl.innerText = 'RECORDING (16x)';
                stateEl.style.color = '#e94560';
                recPauseBtn.innerText = 'PAUSE';
                recPauseBtn.className = 'er-btn-paused';
                onlineIndicator.style.color = '#e94560';
                onlineIndicator.innerText = '● RECORDING';
            } else {
                stateEl.innerText = 'PAUSED';
                stateEl.style.color = '#f57c00';
                recPauseBtn.innerText = 'RESUME';
                recPauseBtn.className = 'er-btn-resume';
                onlineIndicator.style.color = '#f57c00';
                onlineIndicator.innerText = '● PAUSED';
            }
        }
    }

    function setMode(mode) {
        if (mode === 'PASSIVE') {
            isPassive = true;
            isRecording = false;
        }
        updateUI();
    }

    function toggleRecording() {
        if (isPassive) {
            isPassive = false;
            isRecording = true;
        } else {
            isRecording = !isRecording;
        }
        updateUI();
    }

    function clearRam() {
        audioChunks = [];
        totalBytes = 0;
        updateUI();
    }

    function resetAutoDownloadTimer() {
        if (autoDownloadTimer) clearTimeout(autoDownloadTimer);
        if (isRecording && audioChunks.length > 0) {
            autoDownloadTimer = setTimeout(() => {
                downloadAndClear(true);
            }, autoDownloadTimeout);
        }
    }

    function downloadAndClear(auto) {
        if (audioChunks.length === 0) return;

        const blob = new Blob(audioChunks, {
            type: 'audio/mpeg'
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = `ElevenReader_${auto ? 'AUTO_' : ''}${Date.now()}.mp3`;
        document.body.appendChild(a);
        a.click();

        setTimeout(() => {
            window.URL.revokeObjectURL(url);
            clearRam();
        }, 1000);
    }

    window.addEventListener('load', () => {
        injectStyles();
        createUI();
    });

})();