/**
 * FinTrace Dashboard — Frontend Controller
 * ==========================================
 * Handles file uploads, query submissions, result rendering,
 * and dynamic UI updates for the supply chain intelligence dashboard.
 */

(function () {
    'use strict';

    // ═══════════════════════════════════════════════════════════════
    // Configuration
    // ═══════════════════════════════════════════════════════════════

    const API = {
        upload:    '/api/upload/',
        docStatus: (id) => `/api/doc/${id}/status/`,
        query:     '/api/query/',
        graphStats: '/api/graph/stats/',
    };

    const RISK_PERCENT = {
        critical: 92,
        high:     72,
        medium:   48,
        low:      22,
        none:     5,
    };

    const RISK_META = {
        critical: { color: '#ef4444', glow: 'rgba(239,68,68,0.4)',   label: 'CRITICAL',  badgeCls: 'bg-risk-critical risk-critical' },
        high:     { color: '#f97316', glow: 'rgba(249,115,22,0.4)',  label: 'HIGH',      badgeCls: 'bg-risk-high risk-high' },
        medium:   { color: '#eab308', glow: 'rgba(234,179,8,0.4)',   label: 'MEDIUM',    badgeCls: 'bg-risk-medium risk-medium' },
        low:      { color: '#22c55e', glow: 'rgba(34,197,94,0.4)',   label: 'LOW',       badgeCls: 'bg-risk-low risk-low' },
        none:     { color: '#64748b', glow: 'rgba(100,116,139,0.4)', label: 'NONE',      badgeCls: 'bg-risk-none risk-none' },
    };

    const ENTITY_ICONS = {
        Company: '🏢', Supplier: '🏭', Factory: '🏭', Port: '🚢',
        Country: '🌍', City: '🏙️', Region: '🗺️', Product: '📦',
        Vessel: '🚢', Person: '👤', Regulator: '⚖️', Organization: '🏛️',
        Bank: '🏦', Insurer: '🛡️', Terminal: '🏗️', Facility: '🏗️',
        Refinery: '🏭', Market: '📈', Route: '🛣️', Material: '🧱',
        Location: '📍', Exchange: '💱', Waterway: '🌊', Authority: '⚖️',
    };

    const TASK_POLL_INTERVAL = 2500; // ms

    // ═══════════════════════════════════════════════════════════════
    // DOM References
    // ═══════════════════════════════════════════════════════════════

    let $dropZone, $fileInput, $activeUploads, $docsList;
    let $queryInput, $querySubmit, $queryLoading, $emptyState, $resultsSection;
    let $gaugeCircle, $riskPercent, $riskLabel, $riskBadge;
    let $metricEntities, $metricCritical, $metricDepth, $metricDisruptions;
    let $supplyChainPath, $executiveSummary, $reasoningText, $recommendationsList;
    let $entitiesTableBody, $reportTimestamp;
    let $statNodes, $statRels;
    let $reasoningToggle, $reasoningContent, $reasoningChevron;

    // ═══════════════════════════════════════════════════════════════
    // Initialization
    // ═══════════════════════════════════════════════════════════════

    document.addEventListener('DOMContentLoaded', function () {
        // Cache DOM references
        $dropZone        = document.getElementById('drop-zone');
        $fileInput       = document.getElementById('file-input');
        $activeUploads   = document.getElementById('active-uploads');
        $docsList        = document.getElementById('documents-list');
        $queryInput      = document.getElementById('query-input');
        $querySubmit     = document.getElementById('query-submit');
        $queryLoading    = document.getElementById('query-loading');
        $emptyState      = document.getElementById('empty-state');
        $resultsSection  = document.getElementById('results-section');
        $gaugeCircle     = document.getElementById('gauge-circle');
        $riskPercent     = document.getElementById('risk-percent');
        $riskLabel       = document.getElementById('risk-label');
        $riskBadge       = document.getElementById('risk-badge');
        $metricEntities  = document.getElementById('metric-entities');
        $metricCritical  = document.getElementById('metric-critical');
        $metricDepth     = document.getElementById('metric-depth');
        $metricDisruptions = document.getElementById('metric-disruptions');
        $supplyChainPath   = document.getElementById('supply-chain-path');
        $executiveSummary  = document.getElementById('executive-summary');
        $reasoningText     = document.getElementById('reasoning-text');
        $recommendationsList = document.getElementById('recommendations-list');
        $entitiesTableBody   = document.getElementById('entities-table-body');
        $reportTimestamp     = document.getElementById('report-timestamp');
        $statNodes = document.getElementById('stat-nodes');
        $statRels  = document.getElementById('stat-rels');
        $reasoningToggle  = document.getElementById('reasoning-toggle');
        $reasoningContent = document.getElementById('reasoning-content');
        $reasoningChevron = document.getElementById('reasoning-chevron');

        setupDropZone();
        setupQueryForm();
        setupReasoningToggle();
        loadGraphStats();
    });

    // ═══════════════════════════════════════════════════════════════
    // File Upload — Drop Zone
    // ═══════════════════════════════════════════════════════════════

    function setupDropZone() {
        // Click to browse
        $dropZone.addEventListener('click', () => $fileInput.click());
        $fileInput.addEventListener('change', (e) => {
            if (e.target.files.length) handleFiles(e.target.files);
            e.target.value = ''; // reset so same file can be re-uploaded
        });

        // Drag & Drop
        ['dragenter', 'dragover'].forEach(evt =>
            $dropZone.addEventListener(evt, (e) => {
                e.preventDefault();
                e.stopPropagation();
                $dropZone.classList.add('dragover');
            })
        );
        ['dragleave', 'drop'].forEach(evt =>
            $dropZone.addEventListener(evt, (e) => {
                e.preventDefault();
                e.stopPropagation();
                $dropZone.classList.remove('dragover');
            })
        );
        $dropZone.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            if (files.length) handleFiles(files);
        });
    }

    function handleFiles(fileList) {
        const pdfFiles = Array.from(fileList).filter(f => f.name.toLowerCase().endsWith('.pdf'));
        if (pdfFiles.length === 0) {
            showToast('Only PDF files are supported.', 'warning');
            return;
        }

        const formData = new FormData();
        pdfFiles.forEach(f => formData.append('files', f));

        // Show upload items immediately
        $activeUploads.classList.remove('hidden');
        const uploadItems = pdfFiles.map(f => addUploadItem(f.name));

        fetch(API.upload, { method: 'POST', body: formData })
            .then(async r => {
                const contentType = r.headers.get('content-type');
                if (!r.ok || !contentType || !contentType.includes('application/json')) {
                    const text = await r.text();
                    let errMsg = `Server returned HTTP ${r.status}`;
                    try {
                        const errJson = JSON.parse(text);
                        if (errJson && errJson.error) errMsg = errJson.error;
                    } catch (_) {}
                    throw new Error(errMsg);
                }
                return r.json();
            })
            .then(data => {
                if (data.error) {
                    showToast(data.error, 'error');
                    uploadItems.forEach(el => el.remove());
                    return;
                }
                const uploads = data.uploads || [];
                uploads.forEach((u, i) => {
                    if (u.error) {
                        updateUploadItem(uploadItems[i], 'error', u.error);
                    } else if (u.document_id) {
                        // Always poll document status — no Celery/task_id needed
                        updateUploadItem(uploadItems[i], 'processing', 'Processing in background…');
                        pollDocStatus(u.document_id, u.filename, uploadItems[i]);
                    } else {
                        updateUploadItem(uploadItems[i], 'error', 'Invalid upload response');
                    }
                });
                showToast(`${uploads.length} file(s) uploaded — processing…`, 'info');
            })
            .catch(err => {
                showToast('Upload failed: ' + err.message, 'error');
                uploadItems.forEach(el => updateUploadItem(el, 'error', err.message || 'Network error'));
            });
    }

    function addUploadItem(filename) {
        const el = document.createElement('div');
        el.className = 'glass-lighter rounded-lg px-3 py-2.5 fade-in-up';
        el.innerHTML = `
            <div class="flex items-center justify-between gap-2 mb-1.5">
                <p class="text-xs font-medium text-slate-200 truncate flex-1">${escHtml(filename)}</p>
                <span class="upload-status inline-flex items-center gap-1 text-[10px] font-medium text-cyan-400">
                    <span class="w-1.5 h-1.5 rounded-full bg-cyan-400 pulse-dot"></span>Uploading
                </span>
            </div>
            <div class="progress-bar-track progress-indeterminate">
                <div class="progress-bar-fill" style="width: 0%"></div>
            </div>
        `;
        $activeUploads.prepend(el);
        return el;
    }

    function updateUploadItem(el, status, message) {
        const statusEl = el.querySelector('.upload-status');
        const progressTrack = el.querySelector('.progress-bar-track');
        const progressFill = el.querySelector('.progress-bar-fill');

        if (status === 'processing') {
            statusEl.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-cyan-400 pulse-dot"></span>Processing';
            statusEl.className = 'upload-status inline-flex items-center gap-1 text-[10px] font-medium text-cyan-400';
        } else if (status === 'completed') {
            statusEl.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>Completed';
            statusEl.className = 'upload-status inline-flex items-center gap-1 text-[10px] font-medium text-emerald-400';
            progressTrack.classList.remove('progress-indeterminate');
            progressFill.style.width = '100%';
            // Remove after a few seconds
            setTimeout(() => {
                el.style.opacity = '0';
                el.style.transform = 'translateY(-8px)';
                el.style.transition = 'all 0.3s ease';
                setTimeout(() => el.remove(), 350);
            }, 3000);
        } else if (status === 'error') {
            statusEl.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-red-400"></span>${escHtml(message || 'Failed')}`;
            statusEl.className = 'upload-status inline-flex items-center gap-1 text-[10px] font-medium text-red-400';
            progressTrack.classList.remove('progress-indeterminate');
            progressFill.style.width = '0%';
            progressFill.style.background = '#ef4444';
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // Document Status Polling (DB-backed, no Celery/Redis required)
    // ═══════════════════════════════════════════════════════════════

    function pollDocStatus(docId, filename, uploadEl) {
        const poll = () => {
            fetch(API.docStatus(docId))
                .then(async r => {
                    const contentType = r.headers.get('content-type');
                    if (!r.ok || !contentType || !contentType.includes('application/json')) {
                        throw new Error(`HTTP ${r.status}`);
                    }
                    return r.json();
                })
                .then(data => {
                    if (data.ready) {
                        if (data.status === 'completed') {
                            updateUploadItem(uploadEl, 'completed');
                            addDocumentToList(docId, filename, data.result);
                            loadGraphStats();
                            showToast(`✓ ${filename} processed successfully!`, 'success');
                        } else {
                            updateUploadItem(uploadEl, 'error', data.error || 'Processing failed');
                            showToast(`✗ ${filename} failed to process.`, 'error');
                        }
                    } else {
                        // Still processing — show current status and keep polling
                        const statusMsg = data.status === 'processing'
                            ? 'Extracting entities…'
                            : 'Queued…';
                        updateUploadItem(uploadEl, 'processing', statusMsg);
                        setTimeout(poll, TASK_POLL_INTERVAL);
                    }
                })
                .catch(() => {
                    // Network hiccup — retry silently
                    setTimeout(poll, TASK_POLL_INTERVAL * 2);
                });
        };
        setTimeout(poll, TASK_POLL_INTERVAL);
    }

    function addDocumentToList(docId, filename, result) {
        // Remove "no documents" placeholder
        const placeholder = $docsList.querySelector('.italic');
        if (placeholder) placeholder.remove();

        const stats = result || {};
        const el = document.createElement('div');
        el.className = 'glass-lighter rounded-lg px-3 py-2.5 hover-lift fade-in-up';
        el.dataset.docId = docId;
        el.innerHTML = `
            <div class="flex items-start justify-between gap-2">
                <div class="min-w-0 flex-1">
                    <p class="text-xs font-medium text-slate-200 truncate">${escHtml(filename)}</p>
                    <div class="flex items-center gap-2 mt-1">
                        <span class="inline-flex items-center gap-1 text-[10px] font-medium text-emerald-400">
                            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>Completed
                        </span>
                        <span class="text-[10px] text-slate-500">${stats.total_nodes || 0} nodes · ${stats.total_relationships || 0} rels</span>
                    </div>
                </div>
                <span class="text-[10px] text-slate-600 flex-shrink-0">Just now</span>
            </div>
        `;
        $docsList.prepend(el);
    }

    // ═══════════════════════════════════════════════════════════════
    // Risk Query
    // ═══════════════════════════════════════════════════════════════

    function setupQueryForm() {
        $querySubmit.addEventListener('click', submitQuery);
        $queryInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submitQuery();
            }
        });

        // Suggestion chips
        document.querySelectorAll('.suggestion-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                $queryInput.value = chip.dataset.query;
                $queryInput.focus();
            });
        });
    }

    function submitQuery() {
        const question = $queryInput.value.trim();
        if (!question || question.length < 5) {
            showToast('Please enter a question (at least 5 characters).', 'warning');
            return;
        }

        // UI state: loading
        $querySubmit.disabled = true;
        $emptyState.classList.add('hidden');
        $resultsSection.classList.add('hidden');
        $queryLoading.classList.remove('hidden');
        document.getElementById('query-suggestions').classList.add('hidden');

        fetch(API.query, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question }),
        })
            .then(async r => {
                const contentType = r.headers.get('content-type');
                if (!r.ok || !contentType || !contentType.includes('application/json')) {
                    const text = await r.text();
                    let errMsg = `Server returned HTTP ${r.status}`;
                    try {
                        const errJson = JSON.parse(text);
                        if (errJson && errJson.error) errMsg = errJson.error;
                    } catch (_) {}
                    return Promise.reject(new Error(errMsg));
                }
                return r.json();
            })
            .then(data => {
                $queryLoading.classList.add('hidden');
                renderAssessment(data);
            })
            .catch(err => {
                $queryLoading.classList.add('hidden');
                $emptyState.classList.remove('hidden');
                document.getElementById('query-suggestions').classList.remove('hidden');
                const msg = err.error || err.message || 'Query failed';
                showToast('Error: ' + msg, 'error');
            })
            .finally(() => {
                $querySubmit.disabled = false;
            });
    }

    // ═══════════════════════════════════════════════════════════════
    // Result Rendering
    // ═══════════════════════════════════════════════════════════════

    function renderAssessment(data) {
        $resultsSection.classList.remove('hidden');
        $resultsSection.classList.add('fade-in-up');

        const level = (data.overall_risk_level || 'none').toLowerCase();
        const meta = RISK_META[level] || RISK_META.none;
        const percent = RISK_PERCENT[level] || 5;
        const entities = data.impacted_entities || [];
        const disruptions = data.active_disruptions || [];

        // ── Risk Gauge ──────────────────────────────────────────
        const circumference = 2 * Math.PI * 70; // r=70
        const offset = circumference - (percent / 100) * circumference;
        $gaugeCircle.style.setProperty('--gauge-glow', meta.glow);
        $gaugeCircle.setAttribute('stroke', meta.color);

        // Trigger animation with a brief delay
        requestAnimationFrame(() => {
            $gaugeCircle.style.strokeDashoffset = offset;
        });

        animateCounter($riskPercent, percent, '%');
        $riskLabel.textContent = meta.label;
        $riskLabel.style.color = meta.color;

        $riskBadge.textContent = meta.label + ' RISK';
        $riskBadge.className = `text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-full border ${meta.badgeCls}`;

        // ── Metrics ─────────────────────────────────────────────
        const critCount = entities.filter(e => ['critical', 'high'].includes((e.risk_level || '').toLowerCase())).length;
        const maxDepth = entities.length ? Math.max(...entities.map(e => e.depth || 0)) : 0;

        animateCounter($metricEntities, entities.length);
        animateCounter($metricCritical, critCount);
        animateCounter($metricDepth, maxDepth);
        animateCounter($metricDisruptions, disruptions.length);

        // ── Supply Chain Path ───────────────────────────────────
        renderSupplyChainPath(entities);

        // ── Executive Summary ───────────────────────────────────
        $executiveSummary.innerHTML = formatMarkdownLight(data.summary || 'No summary available.');

        // ── Reasoning ───────────────────────────────────────────
        $reasoningText.textContent = data.reasoning || 'No reasoning trace available.';
        // Reset toggle state
        $reasoningContent.classList.add('hidden');
        $reasoningChevron.style.transform = '';

        // ── Recommendations ─────────────────────────────────────
        const recs = data.recommendations || [];
        $recommendationsList.innerHTML = recs.length
            ? recs.map(r => `
                <div class="flex items-start gap-2.5 py-1.5">
                    <svg class="w-4 h-4 text-cyan-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span class="text-sm text-slate-300 leading-relaxed">${escHtml(r)}</span>
                </div>
            `).join('')
            : '<p class="text-xs text-slate-500 italic">No recommendations at this time.</p>';

        // ── Impacted Entities Table ──────────────────────────────
        $entitiesTableBody.innerHTML = entities.length
            ? entities.map(e => {
                const rl = (e.risk_level || 'none').toLowerCase();
                const rm = RISK_META[rl] || RISK_META.none;
                const path = (e.relationship_path || []).join(' → ') || '—';
                return `
                    <tr class="hover:bg-slate-800/20 transition-colors">
                        <td class="py-2 pr-4 text-slate-200 font-medium">${getEntityIcon(e.label)} ${escHtml(e.name)}</td>
                        <td class="py-2 pr-4 text-slate-400">${escHtml(e.label)}</td>
                        <td class="py-2 pr-4 text-slate-400">${e.depth}</td>
                        <td class="py-2 pr-4">
                            <span class="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full border ${rm.badgeCls}">${rm.label}</span>
                        </td>
                        <td class="py-2 text-slate-500 text-[10px] font-mono">${escHtml(path)}</td>
                    </tr>
                `;
            }).join('')
            : '<tr><td colspan="5" class="py-4 text-center text-slate-500 italic">No impacted entities identified.</td></tr>';

        // ── Timestamp ───────────────────────────────────────────
        const ts = data.generated_at ? new Date(data.generated_at).toLocaleString() : new Date().toLocaleString();
        $reportTimestamp.textContent = `Report generated at ${ts}`;
    }

    // ═══════════════════════════════════════════════════════════════
    // Supply Chain Path Visualization
    // ═══════════════════════════════════════════════════════════════

    function renderSupplyChainPath(entities) {
        if (!entities || entities.length === 0) {
            $supplyChainPath.innerHTML = '<p class="text-xs text-slate-500 italic">No dependency path data available.</p>';
            return;
        }

        // Sort by depth, take first entity per depth level
        const sorted = [...entities].sort((a, b) => (a.depth || 0) - (b.depth || 0));
        const byDepth = new Map();
        sorted.forEach(e => {
            if (!byDepth.has(e.depth)) byDepth.set(e.depth, e);
        });
        const chain = Array.from(byDepth.values()).slice(0, 8); // max 8 nodes

        let html = '';
        chain.forEach((entity, idx) => {
            const rl = (entity.risk_level || 'none').toLowerCase();
            const meta = RISK_META[rl] || RISK_META.none;
            const icon = getEntityIcon(entity.label);

            // Node
            html += `
                <div class="chain-node glass-lighter rounded-xl px-4 py-3 text-center border" style="border-color: ${meta.color}30;">
                    <div class="text-xl mb-1">${icon}</div>
                    <p class="text-xs font-semibold text-slate-200 leading-tight mb-0.5">${escHtml(entity.name)}</p>
                    <p class="text-[10px] text-slate-500">${escHtml(entity.label)}</p>
                    <div class="mt-1.5">
                        <span class="text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-full border ${meta.badgeCls}">${meta.label}</span>
                    </div>
                </div>
            `;

            // Arrow between nodes
            if (idx < chain.length - 1) {
                const nextEntity = chain[idx + 1];
                const relLabel = (nextEntity.relationship_path && nextEntity.relationship_path.length)
                    ? nextEntity.relationship_path[nextEntity.relationship_path.length - 1]
                    : '';
                html += `
                    <div class="chain-arrow">
                        <span class="chain-arrow-line">──▶</span>
                        ${relLabel ? `<span class="text-[9px] text-slate-600 font-mono max-w-[80px] truncate" title="${escHtml(relLabel)}">${escHtml(relLabel)}</span>` : ''}
                    </div>
                `;
            }
        });

        $supplyChainPath.innerHTML = html;
    }

    // ═══════════════════════════════════════════════════════════════
    // Reasoning Toggle
    // ═══════════════════════════════════════════════════════════════

    function setupReasoningToggle() {
        $reasoningToggle.addEventListener('click', () => {
            const isHidden = $reasoningContent.classList.contains('hidden');
            $reasoningContent.classList.toggle('hidden');
            $reasoningChevron.style.transform = isHidden ? 'rotate(180deg)' : '';
        });
    }

    // ═══════════════════════════════════════════════════════════════
    // Graph Stats
    // ═══════════════════════════════════════════════════════════════

    function loadGraphStats() {
        fetch(API.graphStats)
            .then(async r => {
                const contentType = r.headers.get('content-type');
                if (!r.ok || !contentType || !contentType.includes('application/json')) {
                    throw new Error(`HTTP ${r.status}`);
                }
                return r.json();
            })
            .then(data => {
                if (data.error) return;
                $statNodes.textContent = formatNumber(data.total_nodes || 0);
                $statRels.textContent = formatNumber(data.total_relationships || 0);
                document.getElementById('graph-stats').classList.remove('hidden');
            })
            .catch(() => { /* silently ignore — stats are optional */ });
    }

    // ═══════════════════════════════════════════════════════════════
    // Toast Notifications
    // ═══════════════════════════════════════════════════════════════

    function showToast(message, type) {
        const container = document.getElementById('toast-container');
        const colors = {
            success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
            error:   'border-red-500/30 bg-red-500/10 text-red-300',
            warning: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
            info:    'border-cyan-500/30 bg-cyan-500/10 text-cyan-300',
        };

        const icons = {
            success: '<path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>',
            error:   '<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"/>',
            warning: '<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/>',
            info:    '<path stroke-linecap="round" stroke-linejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z"/>',
        };

        const toast = document.createElement('div');
        toast.className = `pointer-events-auto flex items-center gap-2.5 px-4 py-3 rounded-lg border backdrop-blur-xl shadow-xl text-sm font-medium toast-enter ${colors[type] || colors.info}`;
        toast.innerHTML = `
            <svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
                ${icons[type] || icons.info}
            </svg>
            <span>${escHtml(message)}</span>
        `;
        container.appendChild(toast);

        setTimeout(() => {
            toast.classList.remove('toast-enter');
            toast.classList.add('toast-exit');
            setTimeout(() => toast.remove(), 350);
        }, 4500);
    }

    // ═══════════════════════════════════════════════════════════════
    // Utility Functions
    // ═══════════════════════════════════════════════════════════════

    function escHtml(str) {
        const div = document.createElement('div');
        div.textContent = str || '';
        return div.innerHTML;
    }

    function getEntityIcon(label) {
        return ENTITY_ICONS[label] || '📍';
    }

    function formatNumber(n) {
        if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
        if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
        return n.toString();
    }

    function animateCounter(el, target, suffix) {
        suffix = suffix || '';
        let current = 0;
        const step = Math.max(1, Math.ceil(target / 30));
        const interval = setInterval(() => {
            current = Math.min(current + step, target);
            el.textContent = current + suffix;
            if (current >= target) clearInterval(interval);
        }, 30);
    }

    function formatMarkdownLight(text) {
        // Minimal markdown rendering: headings, bold, lists, paragraphs
        let html = escHtml(text);

        // Bold
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

        // Headers
        html = html.replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold text-slate-200 mt-4 mb-2">$1</h3>');
        html = html.replace(/^## (.+)$/gm, '<h2 class="text-lg font-semibold text-slate-200 mt-4 mb-2">$1</h2>');
        html = html.replace(/^# (.+)$/gm, '<h1 class="text-xl font-bold text-slate-100 mt-4 mb-2">$1</h1>');

        // Unordered lists
        html = html.replace(/^[-•] (.+)$/gm, '<li class="ml-4 text-slate-300">$1</li>');
        html = html.replace(/(<li[^>]*>.*<\/li>\n?)+/g, (match) => `<ul class="list-disc mb-3">${match}</ul>`);

        // Numbered lists
        html = html.replace(/^\d+\. (.+)$/gm, '<li class="ml-4 text-slate-300">$1</li>');

        // Paragraphs (lines not inside tags)
        html = html.replace(/^(?!<[hulo])((?!<\/)[^\n]+)$/gm, '<p class="text-slate-300 mb-2">$1</p>');

        // Clean up double line breaks
        html = html.replace(/\n{2,}/g, '');
        html = html.replace(/\n/g, '');

        return html;
    }

})();
