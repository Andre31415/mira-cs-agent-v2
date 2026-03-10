// MIRA CS Agent v2 — Frontend JavaScript

const API_BASE = '__PORT_8000__';

// --- Utility functions ---

function formatDate(dateStr) {
    if (!dateStr) return '—';
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString('en-US', {
            month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'
        });
    } catch {
        return dateStr;
    }
}

function badgeClass(value) {
    if (!value) return 'badge';
    const cls = value.toLowerCase().replace(/\s+/g, '_');
    return `badge badge-${cls}`;
}

function badgeLabel(value) {
    if (!value) return '';
    return value.replace(/_/g, ' ');
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function truncate(str, len = 60) {
    if (!str) return '';
    return str.length > len ? str.substring(0, len) + '...' : str;
}

async function api(path, options = {}) {
    const url = `${API_BASE}${path}`;
    const res = await fetch(url, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    });
    if (!res.ok) {
        const text = await res.text();
        throw new Error(`API error ${res.status}: ${text}`);
    }
    return res.json();
}

// --- Toast notifications ---

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container') || createToastContainer();
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.style.cssText = `
        padding: 0.75rem 1rem; margin-bottom: 0.5rem; border-radius: 0.5rem;
        font-size: 0.875rem; animation: fadeIn 0.2s ease;
        ${type === 'success' ? 'background: #16653440; color: #4ade80; border: 1px solid #16653460;' : ''}
        ${type === 'error' ? 'background: #dc262640; color: #f87171; border: 1px solid #dc262660;' : ''}
        ${type === 'info' ? 'background: #1e40af40; color: #60a5fa; border: 1px solid #1e40af60;' : ''}
    `;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

function createToastContainer() {
    const c = document.createElement('div');
    c.id = 'toast-container';
    c.style.cssText = 'position: fixed; top: 1rem; right: 1rem; z-index: 200; width: 320px;';
    document.body.appendChild(c);
    return c;
}

// --- Email Queue Page ---

async function loadEmailQueue(statusFilter = null) {
    const container = document.getElementById('email-table-body');
    if (!container) return;

    container.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem"><div class="spinner"></div></td></tr>';

    try {
        const params = statusFilter ? `?status=${statusFilter}` : '';
        const emails = await api(`/api/emails${params}`);
        const stats = await api('/api/stats');

        // Update stats
        updateStats(stats);

        if (!emails.length) {
            container.innerHTML = `
                <tr><td colspan="6">
                    <div class="empty-state">
                        <h3>No emails found</h3>
                        <p>Run the processor to fetch and process emails.</p>
                    </div>
                </td></tr>`;
            return;
        }

        container.innerHTML = emails.map(email => `
            <tr onclick="showEmailDetail('${escapeHtml(email.id || email.message_id)}')">
                <td>
                    <div style="font-weight:500;color:#f8fafc">${escapeHtml(email.from_name || 'Unknown')}</div>
                    <div style="font-size:0.75rem;color:#64748b">${escapeHtml(email.from_email || '')}</div>
                </td>
                <td class="truncate">${escapeHtml(email.subject || 'No subject')}</td>
                <td><span class="${badgeClass(email.category)}">${badgeLabel(email.category)}</span></td>
                <td><span class="${badgeClass(email.status)}">${badgeLabel(email.status)}</span></td>
                <td>${escapeHtml(email.shopify_order_number || '—')}</td>
                <td>${formatDate(email.received_at)}</td>
            </tr>
        `).join('');
    } catch (err) {
        container.innerHTML = `<tr><td colspan="6" class="empty-state"><p>Error loading emails: ${escapeHtml(err.message)}</p></td></tr>`;
    }
}

function updateStats(stats) {
    const el = (id, val) => {
        const e = document.getElementById(id);
        if (e) e.textContent = val;
    };
    el('stat-total', stats.total_emails || 0);
    el('stat-pending', (stats.email_statuses || {}).pending || 0);
    el('stat-drafted', (stats.email_statuses || {}).draft_created || 0);
    el('stat-tasks', stats.total_tasks || 0);
}

async function showEmailDetail(emailId) {
    try {
        const email = await api(`/api/emails/${emailId}`);
        const modal = document.getElementById('email-modal');
        if (!modal) return;

        // Header
        document.getElementById('modal-subject').textContent = email.subject || 'No subject';
        document.getElementById('modal-from').textContent = `${email.from_name || ''} <${email.from_email || ''}>`;
        document.getElementById('modal-date').textContent = formatDate(email.received_at);
        document.getElementById('modal-category').innerHTML = `<span class="${badgeClass(email.category)}">${badgeLabel(email.category)}</span>`;
        document.getElementById('modal-status').innerHTML = `<span class="${badgeClass(email.status)}">${badgeLabel(email.status)}</span>`;

        // Email body
        document.getElementById('modal-body').textContent = email.body || 'No body';

        // Thread context
        const threadEl = document.getElementById('modal-thread');
        const threadData = email.thread_context;
        if (threadData && Array.isArray(threadData) && threadData.length > 0) {
            threadEl.innerHTML = threadData.map(msg => {
                const fields = msg;
                const isTeam = (fields.from || fields.from_email || '').toLowerCase().includes('trymira.com');
                return `
                    <div style="margin-bottom:0.75rem;padding:0.5rem;border-radius:0.375rem;background:${isTeam ? '#1e40af15' : '#0f172a'}">
                        <div style="font-size:0.75rem;color:${isTeam ? '#60a5fa' : '#94a3b8'};margin-bottom:0.25rem">
                            ${isTeam ? 'Team MIRA' : escapeHtml(fields.from_name || fields.from || 'Customer')} — ${formatDate(fields.date || fields.received_at)}
                        </div>
                        <div style="font-size:0.813rem;color:#cbd5e1;white-space:pre-wrap">${escapeHtml(truncate(fields.body || fields.text || '', 300))}</div>
                    </div>`;
            }).join('');
        } else {
            threadEl.innerHTML = '<span style="color:#64748b">No thread context</span>';
        }

        // Shopify data
        const shopifyEl = document.getElementById('modal-shopify');
        if (email.shopify_data && typeof email.shopify_data === 'object') {
            const o = email.shopify_data;
            shopifyEl.innerHTML = `
                <div class="order-grid">
                    <div class="order-field"><div class="label">Order</div><div class="value">${escapeHtml(o.order_number || '—')}</div></div>
                    <div class="order-field"><div class="label">Fulfillment</div><div class="value">${escapeHtml(o.fulfillment_status || '—')}</div></div>
                    <div class="order-field"><div class="label">Financial</div><div class="value">${escapeHtml(o.financial_status || '—')}</div></div>
                    <div class="order-field"><div class="label">Carrier</div><div class="value">${escapeHtml(o.carrier || '—')} ${escapeHtml(o.shipping_service || '')}</div></div>
                    ${(o.items || []).map(i => `
                        <div class="order-field"><div class="label">Item</div><div class="value">${escapeHtml(i.title)} (${escapeHtml(i.variant || '')})</div></div>
                    `).join('')}
                    ${(o.fulfillments || []).map(f => `
                        <div class="order-field"><div class="label">Shipping</div><div class="value">${escapeHtml(f.display_status || f.status || '—')}</div></div>
                        ${f.delivered_at ? `<div class="order-field"><div class="label">Delivered</div><div class="value">${formatDate(f.delivered_at)}</div></div>` : ''}
                        ${f.estimated_delivery ? `<div class="order-field"><div class="label">Est. Delivery</div><div class="value">${formatDate(f.estimated_delivery)}</div></div>` : ''}
                    `).join('')}
                </div>`;
        } else {
            shopifyEl.innerHTML = '<span style="color:#64748b">No Shopify data</span>';
        }

        // Rules applied
        const rulesEl = document.getElementById('modal-rules');
        const rules = email.rules_applied;
        if (rules && Array.isArray(rules) && rules.length > 0) {
            rulesEl.innerHTML = `<div class="tag-list">${rules.map(r =>
                `<span class="badge badge-general">${escapeHtml(r)}</span>`
            ).join('')}</div>`;
        } else {
            rulesEl.innerHTML = '<span style="color:#64748b">No rules applied</span>';
        }

        // Draft
        const draftEditor = document.getElementById('modal-draft-editor');
        draftEditor.value = email.draft_text || '';
        draftEditor.dataset.emailId = emailId;

        // Show/hide buttons based on status
        const approveBtn = document.getElementById('btn-approve-draft');
        const regenBtn = document.getElementById('btn-regenerate-draft');
        if (approveBtn) approveBtn.style.display = email.draft_text ? '' : 'none';
        if (regenBtn) regenBtn.style.display = '';

        modal.classList.add('active');
    } catch (err) {
        showToast(`Error loading email: ${err.message}`, 'error');
    }
}

function closeModal() {
    const modal = document.getElementById('email-modal');
    if (modal) modal.classList.remove('active');
}

async function saveDraft() {
    const editor = document.getElementById('modal-draft-editor');
    const emailId = editor.dataset.emailId;
    if (!emailId) return;

    try {
        await api(`/api/emails/${emailId}`, {
            method: 'PATCH',
            body: JSON.stringify({ draft_text: editor.value }),
        });
        showToast('Draft saved', 'success');
    } catch (err) {
        showToast(`Error saving draft: ${err.message}`, 'error');
    }
}

async function approveDraft() {
    const editor = document.getElementById('modal-draft-editor');
    const emailId = editor.dataset.emailId;
    if (!emailId) return;

    // Save current text first
    await saveDraft();

    try {
        const btn = document.getElementById('btn-approve-draft');
        btn.disabled = true;
        btn.innerHTML = '<div class="spinner"></div> Creating draft...';

        await api(`/api/drafts/${emailId}/approve`, { method: 'POST' });
        showToast('Gmail draft created!', 'success');
        closeModal();
        loadEmailQueue();
    } catch (err) {
        showToast(`Error creating Gmail draft: ${err.message}`, 'error');
    } finally {
        const btn = document.getElementById('btn-approve-draft');
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = 'Create Gmail Draft';
        }
    }
}

async function regenerateDraft() {
    const editor = document.getElementById('modal-draft-editor');
    const emailId = editor.dataset.emailId;
    if (!emailId) return;

    try {
        const btn = document.getElementById('btn-regenerate-draft');
        btn.disabled = true;
        btn.innerHTML = '<div class="spinner"></div> Generating...';

        const result = await api(`/api/drafts/${emailId}/regenerate`, { method: 'POST' });
        editor.value = result.draft_text || '';
        showToast('Draft regenerated', 'success');
    } catch (err) {
        showToast(`Error regenerating draft: ${err.message}`, 'error');
    } finally {
        const btn = document.getElementById('btn-regenerate-draft');
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = 'Regenerate';
        }
    }
}

// --- Task Tracker Page ---

async function loadTasks(typeFilter = null) {
    const container = document.getElementById('task-table-body');
    if (!container) return;

    container.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem"><div class="spinner"></div></td></tr>';

    try {
        const params = typeFilter ? `?type=${typeFilter}` : '';
        const tasks = await api(`/api/tasks${params}`);

        if (!tasks.length) {
            container.innerHTML = `
                <tr><td colspan="6">
                    <div class="empty-state">
                        <h3>No tasks found</h3>
                        <p>Tasks are created automatically when processing emails.</p>
                    </div>
                </td></tr>`;
            return;
        }

        container.innerHTML = tasks.map(task => {
            const details = typeof task.details === 'string' ? JSON.parse(task.details || '{}') : (task.details || {});
            const statusOptions = getStatusOptions(task.type);
            return `
                <tr>
                    <td>
                        <div style="font-weight:500;color:#f8fafc">${escapeHtml(task.customer_name || 'Unknown')}</div>
                        <div style="font-size:0.75rem;color:#64748b">${escapeHtml(task.customer_email || '')}</div>
                    </td>
                    <td><span class="${badgeClass(task.type)}">${badgeLabel(task.type)}</span></td>
                    <td>${escapeHtml(task.order_number || '—')}</td>
                    <td>
                        <select class="inline-select" onchange="updateTaskStatus(${task.id}, this.value)">
                            ${statusOptions.map(s => `<option value="${s}" ${task.status === s ? 'selected' : ''}>${badgeLabel(s)}</option>`).join('')}
                        </select>
                    </td>
                    <td style="font-size:0.75rem;color:#94a3b8">${formatTaskDetails(details)}</td>
                    <td>${formatDate(task.updated_at)}</td>
                </tr>`;
        }).join('');
    } catch (err) {
        container.innerHTML = `<tr><td colspan="6" class="empty-state"><p>Error: ${escapeHtml(err.message)}</p></td></tr>`;
    }
}

function getStatusOptions(type) {
    switch (type) {
        case 'ring_exchange':
            return ['awaiting_return', 'received', 'awaiting_stock', 'shipped'];
        case 'return_refund':
            return ['inquiry', 'clarification_sent', 'reason_received', 'label_sent', 'item_received', 'refunded'];
        case 'prescription_followup':
            return ['pending', 'submitted', 'shipped'];
        default:
            return ['pending', 'in_progress', 'completed'];
    }
}

function formatTaskDetails(details) {
    if (!details || typeof details !== 'object') return '—';
    const parts = [];
    if (details.old_size) parts.push(`Old: ${details.old_size}`);
    if (details.new_size) parts.push(`New: ${details.new_size}`);
    if (details.reason) parts.push(`Reason: ${truncate(details.reason, 40)}`);
    return parts.length ? parts.join(' | ') : '—';
}

async function updateTaskStatus(taskId, newStatus) {
    try {
        await api(`/api/tasks/${taskId}`, {
            method: 'PATCH',
            body: JSON.stringify({ status: newStatus }),
        });
        showToast(`Task updated to ${badgeLabel(newStatus)}`, 'success');
    } catch (err) {
        showToast(`Error updating task: ${err.message}`, 'error');
        loadTasks();  // Reload to reset
    }
}

// --- Settings Page ---

async function loadSettings() {
    try {
        const settings = await api('/api/settings');
        const toggle = document.getElementById('auto-processing-toggle');
        if (toggle) toggle.checked = settings.auto_processing === 'true';

        // Load recent logs
        loadLogs();
    } catch (err) {
        showToast(`Error loading settings: ${err.message}`, 'error');
    }
}

async function toggleAutoProcessing() {
    const toggle = document.getElementById('auto-processing-toggle');
    try {
        await api('/api/settings', {
            method: 'POST',
            body: JSON.stringify({ auto_processing: toggle.checked ? 'true' : 'false' }),
        });
        showToast(`Auto-processing ${toggle.checked ? 'enabled' : 'disabled'}`, 'success');
    } catch (err) {
        showToast(`Error: ${err.message}`, 'error');
        toggle.checked = !toggle.checked;
    }
}

async function runNow() {
    const btn = document.getElementById('btn-run-now');
    const status = document.getElementById('run-status');

    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div> Processing...';
    if (status) {
        status.innerHTML = '<span class="status-dot yellow"></span>Running...';
        status.style.display = '';
    }

    try {
        const result = await api('/api/run', { method: 'POST' });
        const msg = `Found ${result.emails_found} emails, processed ${result.emails_processed}, created ${result.drafts_created} drafts`;
        showToast(msg, 'success');
        if (status) {
            status.innerHTML = `<span class="status-dot green"></span>${msg}`;
        }
        loadLogs();
    } catch (err) {
        showToast(`Processing failed: ${err.message}`, 'error');
        if (status) {
            status.innerHTML = `<span class="status-dot red"></span>Failed: ${escapeHtml(err.message)}`;
        }
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Run Now';
    }
}

async function loadLogs() {
    const container = document.getElementById('logs-container');
    if (!container) return;

    try {
        const logs = await api('/api/logs');
        if (!logs.length) {
            container.innerHTML = '<div class="empty-state"><p>No processing logs yet.</p></div>';
            return;
        }

        container.innerHTML = logs.map(log => {
            const errors = typeof log.errors === 'string' ? JSON.parse(log.errors || '[]') : (log.errors || []);
            const hasErrors = errors.length > 0;
            return `
                <div class="log-entry">
                    <div class="log-time">${formatDate(log.run_at)}</div>
                    <div class="log-detail">
                        <span class="status-dot ${hasErrors ? 'red' : 'green'}"></span>
                        Found: ${log.emails_found || 0} |
                        Processed: ${log.emails_processed || 0} |
                        Drafts: ${log.drafts_created || 0} |
                        Tasks: ${log.tasks_created || 0} |
                        ${log.duration_ms || 0}ms
                        ${hasErrors ? `<br><span style="color:#f87171;font-size:0.75rem">${errors.map(e => escapeHtml(e)).join('; ')}</span>` : ''}
                    </div>
                </div>`;
        }).join('');
    } catch (err) {
        container.innerHTML = `<div class="empty-state"><p>Error loading logs: ${escapeHtml(err.message)}</p></div>`;
    }
}

// --- Filter chips ---

function setFilter(type, value, loadFn) {
    document.querySelectorAll(`.filter-bar .filter-chip[data-filter-type="${type}"]`).forEach(chip => {
        chip.classList.toggle('active', chip.dataset.filterValue === value);
    });
    loadFn(value || null);
}

// --- Init ---

function initPage() {
    const page = document.body.dataset.page;
    switch (page) {
        case 'emails':
            loadEmailQueue();
            break;
        case 'tasks':
            loadTasks();
            break;
        case 'settings':
            loadSettings();
            break;
    }
}

document.addEventListener('DOMContentLoaded', initPage);
