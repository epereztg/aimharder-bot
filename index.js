const daysOfWeek = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const daysEs = {
    'Monday': 'Lunes',
    'Tuesday': 'Martes',
    'Wednesday': 'Miércoles',
    'Thursday': 'Jueves',
    'Friday': 'Viernes',
    'Saturday': 'Sábado',
    'Sunday': 'Domingo'
};

let currentData = null;
let currentView = 'table';

async function init() {
    setupEventListeners();
    await loadConfig();
}

async function loadConfig() {
    try {
        const response = await fetch('config.json');
        const config = await response.json();

        const selector = document.getElementById('box-selector');
        selector.innerHTML = '';

        for (const file of config.schedules) {
            const res = await fetch(file);
            const data = await res.json();
            const option = document.createElement('option');
            option.value = file;
            option.textContent = data.name || file;
            selector.appendChild(option);

            if (!currentData) {
                currentData = data;
                render();
            }
        }
    } catch (error) {
        console.error('Error loading config:', error);
        document.getElementById('schedule-content').innerHTML = '<div class="error">Error al cargar la configuración. Asegúrate de que config.json y los archivos de horario existen.</div>';
    }
}

function setupEventListeners() {
    document.getElementById('box-selector').addEventListener('change', async (e) => {
        const file = e.target.value;
        try {
            const response = await fetch(file);
            currentData = await response.json();
            render();
        } catch (error) {
            console.error('Error loading schedule:', error);
        }
    });

    document.getElementById('view-table').addEventListener('click', () => switchView('table'));
    document.getElementById('view-list').addEventListener('click', () => switchView('list'));
    document.getElementById('view-calendar').addEventListener('click', () => switchView('calendar'));
}

function switchView(view) {
    currentView = view;
    document.querySelectorAll('.view-toggle button').forEach(btn => btn.classList.remove('active'));
    document.getElementById(`view-${view}`).classList.add('active');
    render();
}

function render() {
    if (!currentData) return;

    const container = document.getElementById('schedule-content');
    container.innerHTML = '';

    if (currentView === 'table') {
        renderTable(container);
    } else if (currentView === 'list') {
        renderList(container);
    } else {
        renderCalendar(container);
    }
}

function renderTable(container) {
    const table = document.createElement('table');
    table.className = 'schedule-table';

    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    daysOfWeek.forEach(day => {
        const th = document.createElement('th');
        th.textContent = daysEs[day];
        headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    const row = document.createElement('tr');

    daysOfWeek.forEach(day => {
        const td = document.createElement('td');
        const classData = currentData[day];

        if (classData) {
            td.innerHTML = `
                <div class="class-card">
                    <span class="class-time">${classData.time}</span>
                    <span class="class-name">${classData.class_name}</span>
                </div>
            `;
        } else {
            td.innerHTML = '<div class="no-class">Sin clases</div>';
        }
        row.appendChild(td);
    });

    tbody.appendChild(row);
    table.appendChild(tbody);
    container.appendChild(table);
}

function renderList(container) {
    const list = document.createElement('div');
    list.className = 'schedule-list';

    daysOfWeek.forEach(day => {
        const classData = currentData[day];
        if (classData) {
            const section = document.createElement('div');
            section.className = 'day-section';
            section.innerHTML = `
                <h3 class="day-title">${daysEs[day]}</h3>
                <div class="class-card">
                    <span class="class-time">${classData.time}</span>
                    <span class="class-name">${classData.class_name}</span>
                </div>
            `;
            list.appendChild(section);
        }
    });

    container.appendChild(list);
}

function renderCalendar(container) {
    const grid = document.createElement('div');
    grid.className = 'calendar-grid';

    daysOfWeek.forEach(day => {
        const classData = currentData[day];
        const dayCard = document.createElement('div');
        dayCard.className = 'calendar-day';

        dayCard.innerHTML = `<span class="day-label">${daysEs[day]}</span>`;

        if (classData) {
            dayCard.innerHTML += `
                <div class="class-card">
                    <span class="class-time">${classData.time}</span>
                    <span class="class-name">${classData.class_name}</span>
                </div>
            `;
        } else {
            dayCard.innerHTML += '<div class="no-class">Sin clases</div>';
        }
        grid.appendChild(dayCard);
    });

    container.appendChild(grid);
}

document.addEventListener('DOMContentLoaded', init);

