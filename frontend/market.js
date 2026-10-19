document.addEventListener('DOMContentLoaded', () => {
    const API_BASE = '/api/v1/markets';
    const PAGE_SIZE = 20;
    const form = document.getElementById('market-filter-form');
    const status = document.getElementById('market-status');
    const tableBody = document.getElementById('market-table-body');
    const previousButton = document.getElementById('previous-page');
    const nextButton = document.getElementById('next-page');
    const pageLabel = document.getElementById('page-label');
    const refreshButton = document.getElementById('refresh-prices');
    const trendChart = document.getElementById('trend-chart');
    const sidebar = document.getElementById('sidebar');
    const sessionsList = document.getElementById('sessions-list');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const collapseSidebarButton = document.getElementById('collapse-sidebar-btn');

    let offset = 0;
    let requestInProgress = false;

    function setupSidebar() {
        const sessions = JSON.parse(localStorage.getItem('agrimitra_sessions') || '[]');
        sessionsList.replaceChildren();
        sessions.slice(0, 12).forEach(session => {
            const item = document.createElement('a');
            item.className = 'session-item';
            item.href = 'chat.html';
            item.addEventListener('click', () => {
                localStorage.setItem('agrimitra_current_session_id', session.id);
            });
            const title = document.createElement('span');
            title.className = 'session-title';
            title.textContent = (session.title || 'Chat').slice(0, 32);
            item.appendChild(title);
            sessionsList.appendChild(item);
        });
        if (!sessions.length) {
            const empty = document.createElement('div');
            empty.className = 'session-title';
            empty.textContent = 'No history';
            sessionsList.appendChild(empty);
        }
        sidebarToggle.addEventListener('click', () => {
            if (window.innerWidth <= 900) sidebar.classList.toggle('open');
            else sidebar.classList.toggle('collapsed');
        });
        collapseSidebarButton.addEventListener('click', () => sidebar.classList.add('collapsed'));
        document.addEventListener('click', event => {
            if (window.innerWidth <= 900
                && sidebar.classList.contains('open')
                && !sidebar.contains(event.target)
                && !sidebarToggle.contains(event.target)) {
                sidebar.classList.remove('open');
            }
        });
    }

    function getFilters() {
        return {
            commodity: document.getElementById('commodity-filter').value.trim(),
            state: document.getElementById('state-filter').value.trim(),
            district: document.getElementById('district-filter').value.trim(),
            market: document.getElementById('market-filter').value.trim(),
            date: document.getElementById('date-filter').value
        };
    }

    function makeUrl(path, params) {
        const url = new URL(`${API_BASE}/${path}`, window.location.origin);
        Object.entries(params).forEach(([key, value]) => {
            if (value !== '' && value !== null && value !== undefined) {
                url.searchParams.set(key, value);
            }
        });
        return url;
    }

    function reportDateTime(value) {
        const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value || '')
            || /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '');
        if (!match) return Number.NEGATIVE_INFINITY;
        const [first, second, third] = match.slice(1).map(Number);
        const day = value.includes('/') ? first : third;
        const month = second;
        const year = value.includes('/') ? third : first;
        const date = new Date(Date.UTC(year, month - 1, day));
        if (
            date.getUTCFullYear() !== year
            || date.getUTCMonth() !== month - 1
            || date.getUTCDate() !== day
        ) return Number.NEGATIVE_INFINITY;
        return date.getTime();
    }

    function latestReportDate(records) {
        return records
            .map(record => record.report_date)
            .filter(Boolean)
            .sort((left, right) => reportDateTime(right) - reportDateTime(left))[0] || null;
    }

    async function requestJson(url) {
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), 35000);
        let response;
        try {
            response = await fetch(url, { signal: controller.signal });
        } catch (error) {
            if (error.name === 'AbortError') {
                throw new Error('The market-data request timed out. Please retry.');
            }
            throw new Error('Could not reach the market-data service. Check your connection and retry.');
        } finally {
            window.clearTimeout(timeout);
        }
        let payload;
        try {
            payload = await response.json();
        } catch {
            throw new Error(`Server returned an invalid response (${response.status}).`);
        }
        if (!response.ok) {
            throw new Error(payload.detail || `Request failed (${response.status}).`);
        }
        return payload;
    }

    function setStatus(message, isError = false) {
        status.textContent = message;
        status.classList.toggle('error', isError);
    }

    function formatPrice(value) {
        if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
        return `₹${Number(value).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
    }

    function makeCell(text, bold = false) {
        const cell = document.createElement('td');
        if (bold) {
            const strong = document.createElement('strong');
            strong.textContent = text || '—';
            cell.appendChild(strong);
        } else {
            cell.textContent = text || '—';
        }
        return cell;
    }

    function renderRecords(records) {
        tableBody.replaceChildren();
        [...records]
            .sort((left, right) => reportDateTime(right.report_date) - reportDateTime(left.report_date))
            .forEach(record => {
            const row = document.createElement('tr');
            row.append(
                makeCell(record.market, true),
                makeCell([record.district, record.state].filter(Boolean).join(', ')),
                makeCell([record.commodity, record.variety, record.grade].filter(Boolean).join(' — ')),
                makeCell(formatPrice(record.min_price)),
                makeCell(formatPrice(record.modal_price)),
                makeCell(formatPrice(record.max_price)),
                makeCell(record.report_date)
            );
            tableBody.appendChild(row);
        });
        if (!records.length) {
            const row = document.createElement('tr');
            const cell = makeCell('No reported records match these filters.');
            cell.colSpan = 7;
            cell.className = 'market-chart-empty';
            row.appendChild(cell);
            tableBody.appendChild(row);
        }
    }

    function renderSummary(records, response, selectedCommodity) {
        if (!selectedCommodity) {
            document.getElementById('summary-min').textContent = 'Select a commodity';
            document.getElementById('summary-modal').textContent = 'Select a commodity';
            document.getElementById('summary-max').textContent = 'Select a commodity';
            document.getElementById('summary-change').textContent = 'Select a commodity';
            const retrievalTime = new Date(response.retrieved_at).toLocaleString();
            document.getElementById('report-meta').textContent =
                `Latest report date in this page: ${latestReportDate(records) || 'not provided'} · Retrieved by AgriMitra: ${retrievalTime} · ${response.source}`;
            return;
        }
        const min = records.map(record => record.min_price).filter(Number.isFinite);
        const modal = records.map(record => record.modal_price).filter(Number.isFinite);
        const max = records.map(record => record.max_price).filter(Number.isFinite);
        document.getElementById('summary-min').textContent = min.length
            ? `${formatPrice(Math.min(...min))} – ${formatPrice(Math.max(...min))} / quintal`
            : 'Not reported';
        document.getElementById('summary-modal').textContent = modal.length
            ? `${formatPrice(Math.min(...modal))} – ${formatPrice(Math.max(...modal))} / quintal`
            : 'Not reported';
        document.getElementById('summary-max').textContent = max.length
            ? `${formatPrice(Math.min(...max))} – ${formatPrice(Math.max(...max))} / quintal`
            : 'Not reported';

        const latestDate = latestReportDate(records);
        const retrievalTime = new Date(response.retrieved_at).toLocaleString();
        document.getElementById('report-meta').textContent = records.length
            ? `Latest report date in this page: ${latestDate || 'not provided'} · Retrieved by AgriMitra: ${retrievalTime} · ${response.source}`
            : `No records returned · Checked: ${retrievalTime} · ${response.source}`;
    }

    function svgElement(name, attributes = {}) {
        const element = document.createElementNS('http://www.w3.org/2000/svg', name);
        Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
        return element;
    }

    function renderTrend(points) {
        trendChart.replaceChildren();
        if (!points.length) {
            const empty = document.createElement('p');
            empty.className = 'market-chart-empty';
            empty.textContent = 'Historical observations are not available yet. Trends will appear after distinct report dates have been retrieved.';
            trendChart.appendChild(empty);
            return;
        }

        const width = Math.max(560, points.length * 54);
        const height = 200;
        const values = points.map(point => point.average_modal_price);
        const minValue = Math.min(...values);
        const maxValue = Math.max(...values);
        const spread = maxValue - minValue || 1;
        const coords = points.map((point, index) => ({
            x: 36 + index * (width - 72) / Math.max(1, points.length - 1),
            y: 150 - ((point.average_modal_price - minValue) / spread) * 108
        }));
        const svg = svgElement('svg', {
            viewBox: `0 0 ${width} ${height}`,
            role: 'img',
            'aria-label': 'Average reported modal prices by report date'
        });
        svg.appendChild(svgElement('line', {
            x1: 30, y1: 152, x2: width - 20, y2: 152,
            stroke: '#d5ddcf', 'stroke-width': 1
        }));
        const line = svgElement('polyline', {
            points: coords.map(point => `${point.x},${point.y}`).join(' '),
            fill: 'none',
            stroke: '#4a6741',
            'stroke-width': 3,
            'stroke-linecap': 'round',
            'stroke-linejoin': 'round'
        });
        svg.appendChild(line);
        coords.forEach((point, index) => {
            svg.appendChild(svgElement('circle', {
                cx: point.x, cy: point.y, r: 4, fill: '#4a6741'
            }));
            const label = svgElement('text', {
                x: point.x, y: 176, 'text-anchor': 'middle',
                fill: '#65725f', 'font-size': 10
            });
            label.textContent = points[index].report_date;
            svg.appendChild(label);
        });
        const minLabel = svgElement('text', { x: 32, y: 32, fill: '#65725f', 'font-size': 11 });
        minLabel.textContent = formatPrice(maxValue);
        svg.appendChild(minLabel);
        const maxLabel = svgElement('text', { x: 32, y: 148, fill: '#65725f', 'font-size': 11 });
        maxLabel.textContent = formatPrice(minValue);
        svg.appendChild(maxLabel);
        trendChart.appendChild(svg);
    }

    async function loadTrend(filters) {
        if (!filters.commodity) {
            renderTrend([]);
            document.getElementById('trend-label').textContent = 'Select a commodity';
            document.getElementById('summary-change').textContent = 'Insufficient history';
            return;
        }
        const trend = await requestJson(makeUrl('trends', {
            commodity: filters.commodity,
            state: filters.state,
            district: filters.district,
            market: filters.market,
            days: 31,
            refresh: filters.refresh ? 'true' : ''
        }));
        renderTrend(trend.points);
        const changeText = days => days === null
            ? 'Not enough report dates'
            : `${days > 0 ? '+' : ''}${days.toFixed(1)}%`;
        document.getElementById('summary-change').textContent =
            `${changeText(trend.change_7d_pct)} / ${changeText(trend.change_30d_pct)}`;
        document.getElementById('trend-label').textContent = trend.points.length
            ? `${trend.points.length} observed report dates · ${trend.unit}`
            : 'No historical records';
    }

    async function loadPrices({ refresh = false } = {}) {
        if (requestInProgress) return;
        requestInProgress = true;
        previousButton.disabled = true;
        nextButton.disabled = true;
        refreshButton.disabled = true;
        setStatus('Loading reported mandi prices…');
        const filters = getFilters();
        filters.refresh = refresh;
        try {
            const response = await requestJson(makeUrl('prices', {
                ...filters,
                limit: PAGE_SIZE,
                offset,
                refresh: refresh ? 'true' : ''
            }));
            renderRecords(response.records);
            renderSummary(response.records, response, filters.commodity);
            const page = Math.floor(offset / PAGE_SIZE) + 1;
            pageLabel.textContent = `Page ${page}${response.total === null ? '' : ` · ${response.total} records`}`;
            previousButton.disabled = offset === 0;
            nextButton.disabled = response.total === null
                ? response.count < PAGE_SIZE
                : offset + response.count >= response.total;
            const resultMessage = response.records.length
                ? `Showing ${response.count} latest available source reports. Prices are reported daily, not live.`
                : 'No records match these filters. Try a broader location, commodity, or report date.';
            setStatus(response.history_saved === false
                ? `${resultMessage} Historical storage failed; trend history may be incomplete.`
                : resultMessage);
            try {
                await loadTrend(filters);
            } catch (error) {
                renderTrend([]);
                document.getElementById('trend-label').textContent = 'Trend could not be loaded';
                document.getElementById('summary-change').textContent = 'Unavailable';
                setStatus(`Prices loaded, but trend history could not be loaded: ${error.message}`, true);
            }
        } catch (error) {
            tableBody.replaceChildren();
            renderTrend([]);
            document.getElementById('summary-min').textContent = '—';
            document.getElementById('summary-modal').textContent = '—';
            document.getElementById('summary-max').textContent = '—';
            document.getElementById('summary-change').textContent = '—';
            document.getElementById('report-meta').textContent = 'No source data was returned.';
            setStatus(`${error.message} Check backend environment configuration and retry.`, true);
            previousButton.disabled = offset === 0;
            nextButton.disabled = true;
        } finally {
            requestInProgress = false;
            refreshButton.disabled = false;
        }
    }

    setupSidebar();
    form.addEventListener('submit', event => {
        event.preventDefault();
        offset = 0;
        loadPrices();
    });
    refreshButton.addEventListener('click', () => loadPrices({ refresh: true }));
    previousButton.addEventListener('click', () => {
        offset = Math.max(0, offset - PAGE_SIZE);
        loadPrices();
    });
    nextButton.addEventListener('click', () => {
        offset += PAGE_SIZE;
        loadPrices();
    });
    loadPrices();
});
