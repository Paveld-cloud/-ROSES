// Инициализация Telegram Web App
let tg = window.Telegram.WebApp;
tg.expand();
tg.enableClosingConfirmation();

// Глобальные переменные
let currentUserId = null;

// Получение ID пользователя из Telegram
if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
    currentUserId = tg.initDataUnsafe.user.id;
}

// DOM элементы
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const rosesList = document.getElementById('rosesList');
const favoritesList = document.getElementById('favoritesList');
const tabBtns = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');
const modal = document.getElementById('roseModal');
const modalBody = document.getElementById('modalBody');
const closeBtn = document.querySelector('.close');

// Обработчики событий
document.addEventListener('DOMContentLoaded', function() {
    loadRoses();
    
    searchBtn.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            performSearch();
        }
    });
    
    // Обработчики вкладок
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Убираем активный класс у всех кнопок и контентов
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            
            // Добавляем активный класс текущей вкладке
            btn.classList.add('active');
            document.getElementById(btn.dataset.tab).classList.add('active');
            
            // Если открыта вкладка избранного - загружаем избранное
            if (btn.dataset.tab === 'favorites') {
                loadFavorites();
            }
        });
    });
    
    // Обработчик модального окна
    closeBtn.addEventListener('click', () => {
        modal.style.display = 'none';
    });
    
    window.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });
});

// Функции загрузки данных
async function loadRoses() {
    showLoading(rosesList);
    try {
        const response = await fetch('/app/search');
        const data = await response.json();
        
        if (data.results) {
            displayRoses(data.results, rosesList);
        } else {
            showError(rosesList, 'Ошибка загрузки роз');
        }
    } catch (error) {
        console.error('Ошибка:', error);
        showError(rosesList, 'Ошибка загрузки данных');
    }
}

async function loadFavorites() {
    if (!currentUserId) {
        showError(favoritesList, 'Не удалось получить данные пользователя');
        return;
    }
    
    showLoading(favoritesList);
    try {
        const response = await fetch(`/app/favorites/${currentUserId}`);
        const data = await response.json();
        
        if (data.favorites) {
            displayRoses(data.favorites, favoritesList);
        } else {
            showError(favoritesList, 'Ошибка загрузки избранного');
        }
    } catch (error) {
        console.error('Ошибка:', error);
        showError(favoritesList, 'Ошибка загрузки данных');
    }
}

function performSearch() {
    const query = searchInput.value.trim();
    showLoading(rosesList);
    
    fetch(`/app/search?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => {
            if (data.results) {
                displayRoses(data.results, rosesList);
            } else {
                showError(rosesList, 'Ошибка поиска');
            }
        })
        .catch(error => {
            console.error('Ошибка:', error);
            showError(rosesList, 'Ошибка поиска');
        });
}

// Функции отображения
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
                <div class="rose-actions">
                    <button class="btn btn-care" onclick="showCare('${encodeURIComponent(rose.name)}')">🪴 Уход</button>
                    <button class="btn btn-history" onclick="showHistory('${encodeURIComponent(rose.name)}')">📜 История</button>
                    <button class="btn btn-favorite" onclick="addToFavorites('${encodeURIComponent(rose.name)}')">⭐</button>
                </div>
            </div>
        </div>
    `).join('');
}

function showCare(roseName) {
    const name = decodeURIComponent(roseName);
    // Здесь можно добавить загрузку полной информации об уходе
    showModal(`🪴 Уход за "${name}"`, `<p>Подробная информация об уходе за розой "${name}" будет здесь.</p>`);
}

function showHistory(roseName) {
    const name = decodeURIComponent(roseName);
    // Здесь можно добавить загрузку истории
    showModal(`📜 История "${name}"`, `<p>История розы "${name}" будет здесь.</p>`);
}

function addToFavorites(roseName) {
    const name = decodeURIComponent(roseName);
    tg.showAlert(`Роза "${name}" добавлена в избранное!`);
    // Здесь можно добавить логику добавления в избранное
}

function showModal(title, content) {
    modalBody.innerHTML = `
        <h2>${title}</h2>
        ${content}
    `;
    modal.style.display = 'block';
}

// Вспомогательные функции
function showLoading(container) {
    container.innerHTML = '<div class="loading">Загрузка...</div>';
}

function showError(container, message) {
    container.innerHTML = `<div class="error">${message}</div>`;
}

function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substr(0, maxLength) + '...';
}

// Добавляем функции в глобальную область видимости
window.showCare = showCare;
window.showHistory = showHistory;
window.addToFavorites = addToFavorites;
