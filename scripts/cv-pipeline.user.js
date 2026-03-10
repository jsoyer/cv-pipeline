// ==UserScript==
// @name         CV Pipeline
// @namespace    https://github.com/janedoe/cv-pipeline
// @version      1.2.0
// @description  One-click "Add to CV Pipeline" button on LinkedIn, Indeed, and Welcome to the Jungle job pages
// @author       janedoe
// @match        https://www.linkedin.com/jobs/view/*
// @match        https://www.linkedin.com/jobs/collections/*
// @match        https://fr.indeed.com/viewjob*
// @match        https://www.indeed.com/viewjob*
// @match        https://www.welcometothejungle.com/*/jobs/*
// @match        https://www.welcometothejungle.com/jobs/*
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_xmlhttpRequest
// @grant        GM_registerMenuCommand
// @connect      localhost
// @connect      127.0.0.1
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    // ---------------------------------------------------------------------------
    // Settings (stored via GM_setValue / GM_getValue)
    // ---------------------------------------------------------------------------

    const SETTINGS = {
        apiUrl:   () => GM_getValue('cv_api_url',  'http://localhost:8765'),
        apiKey:   () => GM_getValue('cv_api_key',  ''),
        provider: () => GM_getValue('cv_provider', 'gemini'),
    };

    function saveSettings(url, key, provider) {
        GM_setValue('cv_api_url',  url);
        GM_setValue('cv_api_key',  key);
        GM_setValue('cv_provider', provider);
    }

    // ---------------------------------------------------------------------------
    // Platform detection
    // ---------------------------------------------------------------------------

    const PLATFORMS = {
        linkedin: /linkedin\.com\/jobs\/(view|collections)\//,
        indeed:   /indeed\.com\/viewjob/,
        wttj:     /welcometothejungle\.com.*\/jobs\//,
    };

    function detectPlatform() {
        const url = window.location.href;
        for (const [name, re] of Object.entries(PLATFORMS)) {
            if (re.test(url)) return name;
        }
        return null;
    }

    // ---------------------------------------------------------------------------
    // Data extractors per platform
    // ---------------------------------------------------------------------------

    function extractLinkedIn() {
        const company =
            document.querySelector('.job-details-jobs-unified-top-card__company-name a')?.innerText?.trim() ||
            document.querySelector('a[data-tracking-control-name="public_jobs_topcard-org-name"]')?.innerText?.trim() ||
            document.querySelector('.jobs-unified-top-card__company-name a')?.innerText?.trim() ||
            '';
        const position =
            document.querySelector('.job-details-jobs-unified-top-card__job-title h1')?.innerText?.trim() ||
            document.querySelector('h1.top-card-layout__title')?.innerText?.trim() ||
            document.querySelector('h1.jobs-unified-top-card__job-title')?.innerText?.trim() ||
            '';
        const description =
            document.querySelector('#job-details')?.innerText?.trim() ||
            document.querySelector('.jobs-description__content')?.innerText?.trim() ||
            document.querySelector('.jobs-description-content__text')?.innerText?.trim() ||
            '';
        return { company, position, description };
    }

    function extractIndeed() {
        const company =
            document.querySelector('[data-testid="inlineHeader-companyName"] a')?.innerText?.trim() ||
            document.querySelector('.jobsearch-CompanyInfoContainer span')?.innerText?.trim() ||
            document.querySelector('[data-company-name]')?.innerText?.trim() ||
            '';
        const position =
            document.querySelector('[data-testid="jobsearch-JobInfoHeader-title"]')?.innerText?.trim() ||
            document.querySelector('h1.jobsearch-JobInfoHeader-title')?.innerText?.trim() ||
            '';
        const description =
            document.querySelector('#jobDescriptionText')?.innerText?.trim() ||
            document.querySelector('.jobsearch-jobDescriptionText')?.innerText?.trim() ||
            '';
        return { company, position, description };
    }

    function extractWTTJ() {
        const company =
            document.querySelector('[data-testid="job-header-company-name"]')?.innerText?.trim() ||
            document.querySelector('[class*="CompanyName"]')?.innerText?.trim() ||
            '';
        const position =
            document.querySelector('[data-testid="job-header-job-name"]')?.innerText?.trim() ||
            document.querySelector('[class*="JobName"] h1')?.innerText?.trim() ||
            document.querySelector('h1')?.innerText?.trim() ||
            '';
        const description =
            document.querySelector('[data-testid="job-section-description"]')?.innerText?.trim() ||
            document.querySelector('[class*="JobDescription"]')?.innerText?.trim() ||
            '';
        return { company, position, description };
    }

    const EXTRACTORS = { linkedin: extractLinkedIn, indeed: extractIndeed, wttj: extractWTTJ };

    // ---------------------------------------------------------------------------
    // Toast notification
    // ---------------------------------------------------------------------------

    function showToast(message, type, duration) {
        type = type || 'info';
        duration = (duration === undefined) ? 5000 : duration;

        document.getElementById('cv-pipeline-toast')?.remove();

        const colors = {
            info:    { bg: '#1A5276', border: '#2E86C1' },
            success: { bg: '#1E8449', border: '#27AE60' },
            error:   { bg: '#922B21', border: '#E74C3C' },
            loading: { bg: '#7D6608', border: '#F1C40F' },
        };
        const c = colors[type] || colors.info;

        const toast = document.createElement('div');
        toast.id = 'cv-pipeline-toast';
        toast.style.cssText = [
            'position:fixed', 'top:20px', 'right:20px', 'z-index:999999',
            'max-width:360px', 'padding:14px 18px', 'border-radius:8px',
            'border-left:4px solid ' + c.border,
            'background:' + c.bg,
            'color:#fff',
            'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
            'font-size:13px', 'line-height:1.5',
            'box-shadow:0 4px 16px rgba(0,0,0,0.4)',
            'transition:opacity 0.3s', 'cursor:pointer',
        ].join(';');
        toast.innerHTML = '<strong>\uD83D\uDCC4 CV Pipeline</strong><br>' + message;
        toast.addEventListener('click', function () { toast.remove(); });
        document.body.appendChild(toast);

        if (duration > 0) {
            setTimeout(function () {
                toast.style.opacity = '0';
                setTimeout(function () { toast.remove(); }, 300);
            }, duration);
        }
        return toast;
    }

    // ---------------------------------------------------------------------------
    // API calls via GM_xmlhttpRequest (bypasses CORS)
    // ---------------------------------------------------------------------------

    function apiRequest(method, endpoint, data) {
        return new Promise(function (resolve, reject) {
            var opts = {
                method: method,
                url: SETTINGS.apiUrl() + endpoint,
                headers: { 'Content-Type': 'application/json' },
                timeout: 300000,
                onload: function (resp) {
                    try {
                        resolve({ status: resp.status, data: JSON.parse(resp.responseText) });
                    } catch (e) {
                        resolve({ status: resp.status, data: { raw: resp.responseText } });
                    }
                },
                onerror: function (err) { reject(new Error('Network error: ' + (err.error || 'unreachable'))); },
                ontimeout: function () { reject(new Error('Request timed out')); },
            };
            if (SETTINGS.apiKey()) opts.headers['X-API-Key'] = SETTINGS.apiKey();
            if (data) opts.data = JSON.stringify(data);
            GM_xmlhttpRequest(opts);
        });
    }

    // ---------------------------------------------------------------------------
    // Pipeline trigger
    // ---------------------------------------------------------------------------

    function triggerPipeline(platform) {
        var extract = EXTRACTORS[platform];
        if (!extract) return;

        var jobData = extract();
        var company = jobData.company;
        var position = jobData.position;
        var description = jobData.description;

        if (!company && !position) {
            showToast('Could not extract job data from this page.<br><small>Try again after the page fully loads.</small>', 'error');
            return;
        }

        var displayName = [company, position].filter(Boolean).join(' \u2014 ');
        showToast('Sending to pipeline\u2026<br><small>' + displayName + '</small>', 'loading', 0);

        // Check health first, then trigger pipeline
        apiRequest('GET', '/health').then(function () {
            return apiRequest('POST', '/pipeline', {
                url:         window.location.href,
                company:     company,
                position:    position,
                description: description,
                provider:    SETTINGS.provider(),
            });
        }).then(function (resp) {
            if (resp.status === 200 && resp.data.status === 'ok') {
                var name = resp.data.name || '?';
                showToast(
                    'Pipeline started!<br><small>' + name + '<br>Check terminal for progress.</small>',
                    'success', 7000
                );
            } else {
                var errStep = (resp.data.steps || []).find(function (s) { return s.rc !== 0; });
                var errMsg = (errStep && errStep.output) || resp.data.error || 'Unknown error';
                showToast('Pipeline error:<br><small>' + String(errMsg).slice(0, 200) + '</small>', 'error', 8000);
            }
        }).catch(function (err) {
            if (err.message.indexOf('unreachable') !== -1 || err.message.indexOf('Network') !== -1) {
                showToast(
                    'Cannot reach cv-api.<br><small>Start it with: <code>make cv-api</code></small>',
                    'error', 8000
                );
            } else {
                showToast('Error: ' + err.message, 'error', 8000);
            }
        });
    }

    // ---------------------------------------------------------------------------
    // Button injection
    // ---------------------------------------------------------------------------

    var BUTTON_CSS = [
        '#cv-pipeline-btn{',
        'display:inline-flex;align-items:center;gap:6px;',
        'padding:8px 14px;margin:6px 0 0 0;',
        'border:1.5px solid #1A5276;border-radius:20px;',
        'background:transparent;color:#1A5276;',
        'font-size:13px;font-weight:600;font-family:inherit;',
        'cursor:pointer;transition:all 0.15s;white-space:nowrap;}',
        '#cv-pipeline-btn:hover{background:#1A5276;color:#fff;}',
        '#cv-pipeline-btn:active{transform:scale(0.97);}',
    ].join('');

    // Platform-specific anchor selectors (ordered by preference)
    var ANCHORS = {
        linkedin: [
            '.job-details-jobs-unified-top-card__primary-description-without-tagline',
            '.jobs-unified-top-card__primary-description',
            '.jobs-apply-button--top-card',
        ],
        indeed: [
            '.jobsearch-IndeedApplyButton-newDesign',
            '.jobsearch-ViewJobButtons-container',
            '#jobDescriptionText',
        ],
        wttj: [
            '[data-testid="job-header-actions"]',
            '[class*="JobActions"]',
            'h1',
        ],
    };

    function injectButton(platform) {
        if (document.getElementById('cv-pipeline-btn')) return;

        var style = document.createElement('style');
        style.textContent = BUTTON_CSS;
        document.head.appendChild(style);

        var btn = document.createElement('button');
        btn.id = 'cv-pipeline-btn';
        btn.innerHTML = '\uD83D\uDCC4 Add to CV Pipeline';
        btn.addEventListener('click', function () { triggerPipeline(platform); });

        var anchors = ANCHORS[platform] || [];
        var inserted = false;

        for (var i = 0; i < anchors.length; i++) {
            var el = document.querySelector(anchors[i]);
            if (el) {
                el.parentNode.insertBefore(btn, el.nextSibling);
                inserted = true;
                break;
            }
        }

        if (!inserted) {
            // Fallback: fixed bottom-right floating button
            btn.style.cssText = [
                'position:fixed', 'bottom:24px', 'right:24px', 'z-index:9999',
                'padding:10px 18px', 'border:none', 'border-radius:24px',
                'background:#1A5276', 'color:#fff',
                'font-size:13px', 'font-weight:600', 'font-family:inherit',
                'cursor:pointer', 'box-shadow:0 3px 12px rgba(0,0,0,0.3)',
            ].join(';');
            document.body.appendChild(btn);
        }
    }

    // ---------------------------------------------------------------------------
    // Settings panel
    // ---------------------------------------------------------------------------

    function showSettings() {
        document.getElementById('cv-pipeline-settings')?.remove();

        var panel = document.createElement('div');
        panel.id = 'cv-pipeline-settings';
        panel.style.cssText = [
            'position:fixed', 'top:50%', 'left:50%',
            'transform:translate(-50%,-50%)',
            'z-index:1000000', 'width:380px',
            'background:#1a1a2e', 'color:#eee',
            'padding:24px', 'border-radius:12px',
            'border:1px solid #2E86C1',
            'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
            'font-size:13px',
            'box-shadow:0 8px 32px rgba(0,0,0,0.6)',
        ].join(';');

        var providers = ['gemini', 'claude', 'openai', 'mistral', 'ollama'];
        var providerOptions = providers.map(function (p) {
            return '<option value="' + p + '"' + (SETTINGS.provider() === p ? ' selected' : '') + '>' + p + '</option>';
        }).join('');

        panel.innerHTML = [
            '<h3 style="margin:0 0 16px;color:#2E86C1;font-size:15px;">\u2699\uFE0F CV Pipeline Settings</h3>',
            '<label style="display:block;margin-bottom:12px;">',
            '  <span style="display:block;margin-bottom:4px;color:#aaa;">API URL</span>',
            '  <input id="cvp-url" type="text" value="' + SETTINGS.apiUrl() + '"',
            '    style="width:100%;box-sizing:border-box;padding:7px 10px;border:1px solid #444;',
            '    border-radius:6px;background:#0d0d1a;color:#eee;font-size:13px;">',
            '</label>',
            '<label style="display:block;margin-bottom:12px;">',
            '  <span style="display:block;margin-bottom:4px;color:#aaa;">API Key (optional)</span>',
            '  <input id="cvp-key" type="password" value="' + SETTINGS.apiKey() + '"',
            '    style="width:100%;box-sizing:border-box;padding:7px 10px;border:1px solid #444;',
            '    border-radius:6px;background:#0d0d1a;color:#eee;font-size:13px;">',
            '</label>',
            '<label style="display:block;margin-bottom:20px;">',
            '  <span style="display:block;margin-bottom:4px;color:#aaa;">AI Provider</span>',
            '  <select id="cvp-provider" style="width:100%;padding:7px 10px;border:1px solid #444;',
            '    border-radius:6px;background:#0d0d1a;color:#eee;font-size:13px;">',
            '    ' + providerOptions,
            '  </select>',
            '</label>',
            '<div style="display:flex;gap:10px;justify-content:flex-end;">',
            '  <button id="cvp-cancel" style="padding:7px 16px;border:1px solid #555;',
            '    border-radius:6px;background:transparent;color:#aaa;cursor:pointer;">Cancel</button>',
            '  <button id="cvp-save" style="padding:7px 16px;border:none;border-radius:6px;',
            '    background:#1A5276;color:#fff;font-weight:600;cursor:pointer;">Save</button>',
            '</div>',
        ].join('');

        document.body.appendChild(panel);

        panel.querySelector('#cvp-cancel').addEventListener('click', function () { panel.remove(); });
        panel.querySelector('#cvp-save').addEventListener('click', function () {
            saveSettings(
                panel.querySelector('#cvp-url').value.trim(),
                panel.querySelector('#cvp-key').value.trim(),
                panel.querySelector('#cvp-provider').value
            );
            panel.remove();
            showToast('Settings saved.', 'success', 3000);
        });
    }

    // ---------------------------------------------------------------------------
    // Initialisation
    // ---------------------------------------------------------------------------

    function init() {
        var platform = detectPlatform();
        if (!platform) return;

        GM_registerMenuCommand('\u2699\uFE0F CV Pipeline Settings', showSettings);
        GM_registerMenuCommand('\uD83D\uDCC4 Add to CV Pipeline', function () { triggerPipeline(platform); });

        if (platform === 'linkedin') {
            // LinkedIn is a SPA — observe DOM until job title appears
            var observer = new MutationObserver(function () {
                var title =
                    document.querySelector('.job-details-jobs-unified-top-card__job-title h1') ||
                    document.querySelector('h1.top-card-layout__title');
                if (title) {
                    injectButton(platform);
                    observer.disconnect();
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });
            // Also try immediately in case page is already loaded
            setTimeout(function () { injectButton(platform); }, 1500);

            // Re-inject on SPA navigation
            var lastUrl = location.href;
            new MutationObserver(function () {
                if (location.href !== lastUrl) {
                    lastUrl = location.href;
                    document.getElementById('cv-pipeline-btn')?.remove();
                    setTimeout(function () { injectButton(platform); }, 1500);
                }
            }).observe(document, { subtree: true, childList: true });
        } else {
            setTimeout(function () { injectButton(platform); }, 800);
        }
    }

    init();

})();
