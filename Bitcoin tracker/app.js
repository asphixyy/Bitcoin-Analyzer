/**
 * Bitcoin Chart Analyzer — Frontend Application
 *
 * Handles:
 *  - Screenshot drag & drop
 *  - OHLCV data entry + paste-from-spreadsheet
 *  - API communication with Flask backend
 *  - Results rendering with animations
 */

// ── Constants ──
const API_BASE = window.location.origin;
const DEFAULT_ROWS = 30;
const MAX_ROWS = 200;

// ── State ──
let selectedTimeframe = '5m';
let screenshotFile = null;
let isAnalyzing = false;

// ── DOM Ready ──
document.addEventListener('DOMContentLoaded', () => {
    initTimeframeSelector();
    initUploadZone();
    initDataTable(DEFAULT_ROWS);
    initPasteArea();
    initAnalyzeButton();
    initSampleDataButton();
    initLiveButton();
    
    // Automatically load live data on page load
    loadLiveData();
});


// ── Timeframe Selector ──
function initTimeframeSelector() {
    const buttons = document.querySelectorAll('.tf-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', () => {
            buttons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            selectedTimeframe = btn.dataset.tf;
        });
    });
}


// ── Screenshot Upload ──
function initUploadZone() {
    const zone = document.getElementById('uploadZone');
    const input = document.getElementById('screenshotInput');
    const removeBtn = zone.querySelector('.remove-btn');

    // Click to upload
    zone.addEventListener('click', (e) => {
        if (e.target === removeBtn || e.target.closest('.remove-btn')) return;
        if (!zone.classList.contains('has-image')) {
            input.click();
        }
    });

    input.addEventListener('change', (e) => {
        if (e.target.files[0]) handleScreenshot(e.target.files[0]);
    });

    // Drag & Drop
    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
    });

    zone.addEventListener('dragleave', () => {
        zone.classList.remove('dragover');
    });

    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('image/')) {
            handleScreenshot(file);
        } else {
            showToast('Please drop an image file', 'error');
        }
    });

    // Remove screenshot
    removeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        removeScreenshot();
    });
}

function handleScreenshot(file) {
    screenshotFile = file;
    const zone = document.getElementById('uploadZone');
    const reader = new FileReader();

    reader.onload = (e) => {
        zone.innerHTML = `
            <button class="remove-btn" onclick="event.stopPropagation(); removeScreenshot();">✕</button>
            <img src="${e.target.result}" alt="Chart screenshot" />
        `;
        zone.classList.add('has-image');
    };
    reader.readAsDataURL(file);
    showToast('Screenshot uploaded', 'success');
}

function removeScreenshot() {
    screenshotFile = null;
    const zone = document.getElementById('uploadZone');
    zone.classList.remove('has-image');
    zone.innerHTML = `
        <button class="remove-btn">✕</button>
        <div class="upload-icon">📊</div>
        <div class="upload-text">Drop your chart screenshot here</div>
        <div class="upload-hint">or click to browse • PNG, JPG, WebP</div>
    `;
    document.getElementById('screenshotInput').value = '';
}


// ── Data Table ──
function initDataTable(rows) {
    const tbody = document.getElementById('dataTableBody');
    tbody.innerHTML = '';

    for (let i = 0; i < rows; i++) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${i + 1}</td>
            <td><input type="number" step="any" placeholder="Open" data-col="open" data-row="${i}" /></td>
            <td><input type="number" step="any" placeholder="High" data-col="high" data-row="${i}" /></td>
            <td><input type="number" step="any" placeholder="Low" data-col="low" data-row="${i}" /></td>
            <td><input type="number" step="any" placeholder="Close" data-col="close" data-row="${i}" /></td>
            <td><input type="number" step="any" placeholder="Vol" data-col="volume" data-row="${i}" /></td>
        `;
        tbody.appendChild(tr);
    }
    updateCandleCount();
}

function updateCandleCount() {
    const inputs = document.querySelectorAll('#dataTableBody input[data-col="close"]');
    let filled = 0;
    inputs.forEach(inp => {
        if (inp.value.trim() !== '') filled++;
    });
    const countEl = document.getElementById('candleCount');
    if (countEl) {
        countEl.textContent = `${filled} candles`;
        countEl.style.color = filled >= 50 ? 'var(--bullish)' : filled >= 10 ? 'var(--neutral-yellow)' : 'var(--text-muted)';
    }
}

// Listen to input changes for count
document.addEventListener('input', (e) => {
    if (e.target.matches('#dataTableBody input')) {
        updateCandleCount();
    }
});


// ── Paste Area ──
function initPasteArea() {
    const pasteArea = document.getElementById('pasteArea');
    if (!pasteArea) return;

    pasteArea.addEventListener('paste', (e) => {
        // Short delay to let the paste populate
        setTimeout(() => parsePastedData(pasteArea.value), 50);
    });

    pasteArea.addEventListener('input', () => {
        // Debounce
        clearTimeout(pasteArea._debounce);
        pasteArea._debounce = setTimeout(() => {
            if (pasteArea.value.trim()) {
                parsePastedData(pasteArea.value);
            }
        }, 500);
    });
}

function parsePastedData(text) {
    const lines = text.trim().split('\n').filter(l => l.trim());
    if (lines.length === 0) return;

    const candles = [];
    for (const line of lines) {
        // Support tab-separated, comma-separated, or space-separated
        const parts = line.split(/[\t,;|]+/).map(s => s.trim()).filter(s => s);

        if (parts.length >= 4) {
            // Try to detect if first column is timestamp/index
            let startIdx = 0;
            const firstVal = parseFloat(parts[0]);

            // If first value looks like a timestamp (>1000000000) or index, skip it
            if (parts.length >= 5 && (firstVal > 1000000000 || (Number.isInteger(firstVal) && firstVal < 1000))) {
                startIdx = 1;
            }

            const open = parseFloat(parts[startIdx]);
            const high = parseFloat(parts[startIdx + 1]);
            const low = parseFloat(parts[startIdx + 2]);
            const close = parseFloat(parts[startIdx + 3]);
            const volume = parts.length > startIdx + 4 ? parseFloat(parts[startIdx + 4]) : 1.0;

            if (!isNaN(open) && !isNaN(high) && !isNaN(low) && !isNaN(close)) {
                candles.push({ open, high, low, close, volume: isNaN(volume) ? 1.0 : volume });
            }
        }
    }

    if (candles.length > 0) {
        fillTableFromCandles(candles);
        showToast(`Parsed ${candles.length} candles from pasted data`, 'success');
    } else {
        showToast('Could not parse candle data. Use format: Open, High, Low, Close, Volume', 'error');
    }
}

function fillTableFromCandles(candles) {
    const tbody = document.getElementById('dataTableBody');
    // Ensure enough rows
    const currentRows = tbody.querySelectorAll('tr').length;
    if (candles.length > currentRows) {
        initDataTable(candles.length);
    }

    const rows = tbody.querySelectorAll('tr');
    candles.forEach((c, i) => {
        if (i < rows.length) {
            const inputs = rows[i].querySelectorAll('input');
            inputs[0].value = c.open;
            inputs[1].value = c.high;
            inputs[2].value = c.low;
            inputs[3].value = c.close;
            inputs[4].value = c.volume;
        }
    });

    // Also feed raw text directly into the paste/input area
    const pasteArea = document.getElementById('pasteArea');
    if (pasteArea) {
        const lines = candles.map(c => `${c.open}, ${c.high}, ${c.low}, ${c.close}, ${c.volume}`);
        pasteArea.value = lines.join('\n');
    }

    updateCandleCount();
}


// ── Sample Data ──
function initSampleDataButton() {
    const btn = document.getElementById('sampleDataBtn');
    if (!btn) return;

    btn.addEventListener('click', () => {
        loadSampleData();
    });
}

function loadSampleData() {
    // Generate realistic BTC sample data around $63,000-$64,000
    const candles = [];
    let price = 63200;

    for (let i = 0; i < 60; i++) {
        const change = (Math.random() - 0.48) * 150; // Slight bullish bias
        const open = price;
        const close = price + change;
        const high = Math.max(open, close) + Math.random() * 80;
        const low = Math.min(open, close) - Math.random() * 80;
        const volume = 0.1 + Math.random() * 2;

        candles.push({
            open: Math.round(open * 100) / 100,
            high: Math.round(high * 100) / 100,
            low: Math.round(low * 100) / 100,
            close: Math.round(close * 100) / 100,
            volume: Math.round(volume * 10000) / 10000,
        });
        price = close;
    }

    fillTableFromCandles(candles);
    showToast('Loaded 60 sample candles (simulated BTC data)', 'info');
}


// ── Live Data ──
function initLiveButton() {
    const btn = document.getElementById('liveDataBtn');
    if (!btn) return;

    btn.addEventListener('click', () => {
        loadLiveData();
    });
}

async function loadLiveData() {
    const btn = document.getElementById('liveDataBtn');
    if (!btn) return;

    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '⌛ Fetching...';

    try {
        const url = `${API_BASE}/api/fetch-live?timeframe=${selectedTimeframe}&limit=100`;
        const response = await fetch(url);
        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || 'Failed to fetch live data');
        }

        const candles = data.candles;
        if (candles && candles.length > 0) {
            fillTableFromCandles(candles);
            
            // Sync selected timeframe button visually
            const tfButtons = document.querySelectorAll('.tf-btn');
            tfButtons.forEach(b => {
                if (b.dataset.tf === data.timeframe) {
                    b.classList.add('active');
                } else {
                    b.classList.remove('active');
                }
            });
            selectedTimeframe = data.timeframe;

            let detailsMsg = `Fetched 100 live ${data.timeframe} candles. Price: $${data.current_price.toLocaleString()}`;
            if (data.ticker_24h) {
                const pct = data.ticker_24h.price_change_pct;
                detailsMsg += ` (${pct >= 0 ? '+' : ''}${pct.toFixed(2)}% 24h)`;
            }
            showToast(detailsMsg, 'success');
        } else {
            showToast('No candle data returned from API.', 'error');
        }
    } catch (error) {
        console.error('Error fetching live data:', error);
        showToast(error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}


// ── Add/Clear Rows ──
function addRows(count) {
    const tbody = document.getElementById('dataTableBody');
    const currentRows = tbody.querySelectorAll('tr').length;

    for (let i = 0; i < count; i++) {
        const idx = currentRows + i;
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${idx + 1}</td>
            <td><input type="number" step="any" placeholder="Open" data-col="open" data-row="${idx}" /></td>
            <td><input type="number" step="any" placeholder="High" data-col="high" data-row="${idx}" /></td>
            <td><input type="number" step="any" placeholder="Low" data-col="low" data-row="${idx}" /></td>
            <td><input type="number" step="any" placeholder="Close" data-col="close" data-row="${idx}" /></td>
            <td><input type="number" step="any" placeholder="Vol" data-col="volume" data-row="${idx}" /></td>
        `;
        tbody.appendChild(tr);
    }
}

function clearTable() {
    initDataTable(DEFAULT_ROWS);
    const pasteArea = document.getElementById('pasteArea');
    if (pasteArea) pasteArea.value = '';
    showToast('Table cleared', 'info');
}


// ── Analyze ──
function initAnalyzeButton() {
    const btn = document.getElementById('analyzeBtn');
    btn.addEventListener('click', () => runAnalysis());
}

async function runAnalysis() {
    if (isAnalyzing) return;

    // Collect candles from table
    const candles = collectCandles();
    if (candles.length < 10) {
        showToast(`Need at least 10 candles. You have ${candles.length}. Add more data or use "Load Sample Data".`, 'error');
        return;
    }

    isAnalyzing = true;
    const btn = document.getElementById('analyzeBtn');
    btn.classList.add('loading');
    btn.disabled = true;

    // Show loading state in results
    const resultsPanel = document.getElementById('resultsContent');
    resultsPanel.innerHTML = '<div class="shimmer"></div>';

    try {
        const response = await fetch(`${API_BASE}/api/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                candles: candles,
                timeframe: selectedTimeframe,
            }),
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Analysis failed');
        }

        renderResults(data);
        showToast('Analysis complete', 'success');

    } catch (error) {
        console.error('Analysis error:', error);
        resultsPanel.innerHTML = `<div class="error-message">⚠️ ${error.message}</div>`;
        showToast(error.message, 'error');
    } finally {
        isAnalyzing = false;
        btn.classList.remove('loading');
        btn.disabled = false;
    }
}

function collectCandles() {
    const tbody = document.getElementById('dataTableBody');
    const rows = tbody.querySelectorAll('tr');
    const candles = [];

    rows.forEach(row => {
        const inputs = row.querySelectorAll('input');
        const open = parseFloat(inputs[0].value);
        const high = parseFloat(inputs[1].value);
        const low = parseFloat(inputs[2].value);
        const close = parseFloat(inputs[3].value);
        const volume = parseFloat(inputs[4].value);

        if (!isNaN(open) && !isNaN(high) && !isNaN(low) && !isNaN(close)) {
            candles.push({
                open,
                high,
                low,
                close,
                volume: isNaN(volume) ? 1.0 : volume,
            });
        }
    });

    return candles;
}


// ── Results Rendering ──
function renderResults(data) {
    const panel = document.getElementById('resultsContent');

    const dirClass = data.direction.toLowerCase();
    const arrow = data.direction === 'LONG' ? '↑' : data.direction === 'SHORT' ? '↓' : '→';
    const dirIcon = data.direction === 'LONG' ? '🟢' : data.direction === 'SHORT' ? '🔴' : '🟡';

    // Build the confidence gauge SVG
    const circumference = 2 * Math.PI * 42;
    const offset = circumference - (data.confidence / 100) * circumference;
    const gaugeColor = data.direction === 'LONG' ? 'var(--bullish)' :
                       data.direction === 'SHORT' ? 'var(--bearish)' : 'var(--neutral-yellow)';

    let html = `
        <!-- Signal Hero -->
        <div class="signal-hero ${dirClass} fade-in-up">
            <span class="signal-arrow">${arrow}</span>
            <div class="signal-direction">${dirIcon} ${data.direction}</div>
            <div class="signal-meta">
                Composite score: ${data.composite_score > 0 ? '+' : ''}${data.composite_score.toFixed(4)} •
                ${data.candles_analyzed} candles analyzed on ${data.input_timeframe}
            </div>

            <div class="confidence-section">
                <div class="gauge-container">
                    <svg viewBox="0 0 100 100">
                        <circle class="gauge-bg" cx="50" cy="50" r="42" />
                        <circle class="gauge-fill" cx="50" cy="50" r="42"
                            stroke="${gaugeColor}"
                            stroke-dasharray="${circumference}"
                            stroke-dashoffset="${offset}" />
                    </svg>
                    <div class="gauge-text">
                        <div class="gauge-value" style="color: ${gaugeColor}">${data.confidence}%</div>
                        <div class="gauge-label">Confidence</div>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Recommended timeframe
    if (data.recommended_timeframe) {
        const tf = data.recommended_timeframe;
        html += `
        <div class="card fade-in-up fade-in-up-1">
            <div class="card-header">
                <div class="icon">⏱️</div>
                <h2>Recommended Timeframe</h2>
            </div>
            <div class="tf-recommendation">
                <div class="tf-icon">📈</div>
                <div class="tf-info">
                    <h4>${tf.timeframe}</h4>
                    <p>${tf.reason}</p>
                    <p class="hold-dur">Hold: ${tf.hold_duration}</p>
                </div>
            </div>
        </div>
        `;
    }

    // Trade Plan
    if (data.trade_plan && Object.keys(data.trade_plan).length > 0) {
        const tp = data.trade_plan;
        html += `
        <div class="card fade-in-up fade-in-up-2">
            <div class="card-header">
                <div class="icon">🎯</div>
                <h2>Trade Plan</h2>
                <span class="badge">${data.direction}</span>
            </div>
            <div class="trade-plan-grid">
                <div class="plan-item entry">
                    <div class="plan-label">Entry Zone</div>
                    <div class="plan-value">${tp.entry_zone}</div>
                </div>
                <div class="plan-item stop">
                    <div class="plan-label">Stop Loss</div>
                    <div class="plan-value">${tp.stop_loss}</div>
                </div>
                <div class="plan-item target">
                    <div class="plan-label">Take Profit 1</div>
                    <div class="plan-value">${tp.take_profit_1}</div>
                </div>
                <div class="plan-item target">
                    <div class="plan-label">Take Profit 2</div>
                    <div class="plan-value">${tp.take_profit_2}</div>
                </div>
            </div>
            <div style="margin-top: 12px; text-align: center;">
                <span class="sr-chip" style="border-color: var(--btc-orange);">Risk/Reward: ${tp.risk_reward}</span>
            </div>
        </div>
        `;
    }

    // Indicators
    html += `
    <div class="card fade-in-up fade-in-up-3">
        <div class="card-header">
            <div class="icon">📉</div>
            <h2>Technical Indicators</h2>
            <span class="badge">${data.indicators.length} active</span>
        </div>
        <div class="indicators-grid">
    `;

    data.indicators.forEach((ind, idx) => {
        const scoreClass = ind.signal > 0.1 ? 'bullish' : ind.signal < -0.1 ? 'bearish' : 'neutral';
        const scoreText = ind.signal > 0 ? `+${ind.signal.toFixed(3)}` : ind.signal.toFixed(3);
        const barWidth = Math.abs(ind.signal) * 50; // Max 50% from center

        let detailsHtml = '';
        if (ind.details && Object.keys(ind.details).length > 0) {
            for (const [key, val] of Object.entries(ind.details)) {
                const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                detailsHtml += `
                    <div class="detail-row">
                        <span class="detail-key">${label}</span>
                        <span class="detail-val">${typeof val === 'number' ? val.toLocaleString() : val}</span>
                    </div>
                `;
            }
        }

        html += `
        <div class="indicator-card" id="ind-${idx}">
            <div class="indicator-header" onclick="toggleIndicator(${idx})">
                <span class="ind-name">${ind.name}</span>
                <span class="ind-score ${scoreClass}">${scoreText}</span>
                <span class="expand-icon">▼</span>
            </div>
            <div class="ind-bar-track">
                <div class="ind-bar-center"></div>
                <div class="ind-bar-fill ${ind.signal >= 0 ? 'positive' : 'negative'}"
                     style="width: ${barWidth}%"></div>
            </div>
            <div class="indicator-details">
                ${detailsHtml}
                <div class="ind-status">${ind.status}</div>
            </div>
        </div>
        `;
    });

    html += `</div></div>`;

    // Support/Resistance
    if (data.support_resistance && data.support_resistance.length > 0) {
        html += `
        <div class="card fade-in-up fade-in-up-4">
            <div class="card-header">
                <div class="icon">📊</div>
                <h2>Key Price Levels</h2>
                <span class="badge">Historical S/R</span>
            </div>
            <div class="sr-levels">
        `;
        data.support_resistance.forEach(level => {
            const isAbove = level.price > data.current_price;
            const color = isAbove ? 'var(--bearish)' : 'var(--bullish)';
            html += `<span class="sr-chip" style="border-color: ${color}; color: ${color};">
                $${level.price.toLocaleString()} ${isAbove ? '▲ R' : '▼ S'}
            </span>`;
        });
        html += `</div></div>`;
    }

    panel.innerHTML = html;

    // Scroll results into view on mobile
    if (window.innerWidth < 1100) {
        panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

function toggleIndicator(idx) {
    const card = document.getElementById(`ind-${idx}`);
    card.classList.toggle('expanded');
}


// ── Toast Notifications ──
function showToast(message, type = 'info') {
    // Remove existing toasts
    document.querySelectorAll('.toast').forEach(t => t.remove());

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(50px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}
