// Инициализация Telegram Web App
let tg = window.Telegram.WebApp;

// DOM элементы
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const rosesList = document.getElementById('rosesList');

// Функции загрузки данных
async function loadRoses(query = '') {
    showLoading(rosesList);
    try {
        const response = await fetch(`/api/roses?search=${encodeURIComponent(query)}`);
        const data = await response.json();
        
        if (data.roses) {
            displayRoses(data.roses, rosesList);
        } else {
            showError(rosesList, 'Ошибка загрузки роз');
        }
    } catch (error) {
        console.error('Ошибка:', error);
        showError(rosesList, 'Ошибка загрузки данных');
    }
}

function showLoading(container) {
    container.innerHTML = '<div class="loading">Загрузка...</div>';
}

function showError(container, message) {
    container.innerHTML = `<div class="error">${message}</div>`;
}

function displayRoses(roses, container) {
    if (roses.length === 0) {
        container.innerHTML = '<div class="error">Розы не найдены</div>';
        return;
    }
    
    container.innerHTML = roses.map(rose => `
        <div class="rose-card">
            ${rose.photo ? `<img src="${rose.photo}" alt="${rose.name}" class="rose-image" onerror="this.style.display='none'">` : ''}
            <div class="rose-info">
                <h3 class="rose-name">${rose.name}</h3>
                <p class="rose-description">${truncateText(rose.description, 100)}</p>
            </div>
        </div>
    `).join('');
}

function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

// Обработчики событий
document.addEventListener('DOMContentLoaded', function() {
    loadRoses();
    
    searchBtn.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            performSearch();
        }
    });
});

function performSearch() {
    const query = searchInput.value.trim();
    loadRoses(query);
}
