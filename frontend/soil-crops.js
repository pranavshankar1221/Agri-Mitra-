document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const collapseSidebarBtn = document.getElementById('collapse-sidebar-btn');
    const sessionsList = document.getElementById('sessions-list');

    const soilSelect = document.getElementById('soil-select');
    const seasonSelect = document.getElementById('season-select');
    const calculateBtn = document.getElementById('btn-calculate');
    const resultsContainer = document.getElementById('calc-results');
    const resultsHeading = document.getElementById('results-heading');
    const rotationTimeline = document.getElementById('rotation-timeline');

    // Sidebar sessions loading (unified with chat)
    let sessions = JSON.parse(localStorage.getItem('agrimitra_sessions')) || [];
    initSidebar();

    function initSidebar() {
        renderSessionsList();
        setupSidebarListeners();
    }

    function setupSidebarListeners() {
        // Toggle mobile sidebar
        sidebarToggle.addEventListener('click', () => {
            if (window.innerWidth <= 900) {
                sidebar.classList.toggle('open');
            } else {
                sidebar.classList.toggle('collapsed');
            }
        });

        // Collapse Sidebar button
        if (collapseSidebarBtn) {
            collapseSidebarBtn.addEventListener('click', () => {
                sidebar.classList.add('collapsed');
            });
        }

        // Close sidebar clicking outside
        document.addEventListener('click', (e) => {
            if (window.innerWidth <= 900 && 
                sidebar.classList.contains('open') && 
                !sidebar.contains(e.target) && 
                !sidebarToggle.contains(e.target)) {
                sidebar.classList.remove('open');
            }
        });
    }

    function renderSessionsList() {
        sessionsList.innerHTML = '';
        if (sessions.length === 0) {
            sessionsList.innerHTML = '<div style="padding: 1rem 1.4rem; font-size: 0.8rem; color: var(--text-secondary); opacity: 0.5;">No history</div>';
            return;
        }

        sessions.forEach(session => {
            const item = document.createElement('div');
            item.className = 'session-item';
            item.setAttribute('data-id', session.id);
            
            let displayTitle = session.title;
            if (displayTitle.length > 22) {
                displayTitle = displayTitle.substring(0, 20) + '...';
            }

            item.innerHTML = `
                <div class="session-info">
                    <span class="session-icon">💬</span>
                    <span class="session-title" title="${session.title}">${displayTitle}</span>
                </div>
            `;

            // Click session -> load and redirect to chat
            item.addEventListener('click', () => {
                localStorage.setItem('agrimitra_current_session_id', session.id);
                window.location.href = 'chat.html';
            });

            sessionsList.appendChild(item);
        });
    }

    // Crop Suitability data based on Soil + Season combinations
    const suitabilityData = {
        'sandy-loam': {
            title: 'Sandy Loam Crop Rotation Plan',
            phases: [
                { phase: '1. Kharif', crop: 'Maize or Pearl Millet (Bajra)', desc: 'Excellent growth in well-drained sandy loam. Contributes organic carbon to soil.' },
                { phase: '2. Rabi', crop: 'Mustard or Chickpea (Gram)', desc: 'Deep taproots improve soil structure. Chickpeas fix nitrogen in the root nodules.' },
                { phase: '3. Zaid', crop: 'Cowpea (Lobia) or Moong Dal', desc: 'Fast-growing cover crop. Acts as green manure to replenish nitrogen and prevents summer soil erosion.' }
            ]
        },
        'clayey': {
            title: 'Clayey Soil Crop Rotation Plan',
            phases: [
                { phase: '1. Kharif', crop: 'Paddy (Rice)', desc: 'High clay content retains standing water perfectly, ideal for early rice transplantation.' },
                { phase: '2. Rabi', crop: 'Lentils or Linseed', desc: 'Thrives on the heavy residual moisture stored in the clay layer during winter.' },
                { phase: '3. Zaid', crop: 'Fallow / Sesame', desc: 'Soil should rest or grow light sesame to restore soil aeration and structure.' }
            ]
        },
        'black-cotton': {
            title: 'Black Cotton Soil Crop Rotation Plan',
            phases: [
                { phase: '1. Kharif', crop: 'Cotton or Soybean', desc: 'Moisture-retaining black clayey soil is highly suited for deep-rooted long-staple cotton.' },
                { phase: '2. Rabi', crop: 'Durum Wheat or Bengal Gram', desc: 'Utilizes deep soil moisture. Yields rich grain under cold conditions.' },
                { phase: '3. Zaid', crop: 'Green Manuring (Dhaincha)', desc: 'Ploughed back into the soil before Kharif to increase organic carbon and soil porosity.' }
            ]
        },
        'alluvial': {
            title: 'Alluvial Soil Crop Rotation Plan',
            phases: [
                { phase: '1. Kharif', crop: 'Sugarcane or Maize', desc: 'Thrives in river-basin soils rich in minerals. Highly productive cash returns.' },
                { phase: '2. Rabi', crop: 'Wheat or Potato', desc: 'Loose alluvial silt allows perfect tuber growth for potato and high densities of winter wheat.' },
                { phase: '3. Zaid', crop: 'Summer Vegetables or Moong Dal', desc: 'Short-duration vegetable crop (melons, gourds) brings quick cash flow.' }
            ]
        }
    };

    // Calculate Suitability action
    calculateBtn.addEventListener('click', () => {
        const soil = soilSelect.value;
        const plan = suitabilityData[soil];

        if (plan) {
            resultsHeading.textContent = plan.title;
            rotationTimeline.innerHTML = '';

            plan.phases.forEach(item => {
                const phaseRow = document.createElement('div');
                phaseRow.className = 'timeline-phase';
                phaseRow.innerHTML = `
                    <span class="phase-tag">${item.phase}:</span>
                    <span class="phase-text"><strong>${item.crop}</strong> — ${item.desc}</span>
                `;
                rotationTimeline.appendChild(phaseRow);
            });

            // Show results section
            resultsContainer.style.display = 'block';
        }
    });
});
