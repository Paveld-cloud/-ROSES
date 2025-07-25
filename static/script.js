// Инициализация Telegram Web App
let tg = window.Telegram.WebApp;

// DOM элементы
const favoritesList = document.getElementById('favoritesList');

// Функция загрузки избранного
async function loadFavorites(chatId) {
    showLoading(favoritesList);
    try {
        const response = await fetch(`/app/favorites?chat_id=${chatId}`);
        const data = await response.json();
        
        if (data.favorites) {
            displayFavorites(data.favorites, favoritesList);
        } else {
            showError(favoritesList, 'Ошибка загрузки избранного: ' + (data.error || 'Неизвестная ошибка'));
        }
    } catch (error) {
        console.error('Ошибка:', error);
        showError(favoritesList, 'Ошибка загрузки данных: ' + error.message);
    }
}

function showLoading(container) {
    container.innerHTML = '<div class="loading">Загрузка избранного...</div>';
}

function showError(container, message) {
    container.innerHTML = `<div class="error">${message}</div>`;
}

function displayFavorites(favorites, container) {
    if (favorites.length === 0) {
        container.innerHTML = '<div class="empty-state">💔 У вас нет избранных роз</div>';
        return;
    }
    
    container.innerHTML = favorites.map(rose => `
        <div class="rose-card">
            ${rose.photo ? `<img src="${rose.photo}" alt="${rose.name}" class="rose-image" onerror="this.style.display='none'">` : ''}
            <div class="rose-info">
                <h3 class="rose-name">${rose.name}</h3>
                <p class="rose-description">${truncateText(rose.description, 100)}</p>
                <div class="rose-actions">
                    <button class="btn btn-care" onclick="showCare('${rose.id}')">🪴 Уход</button>
                    <button class="btn btn-history" onclick="showHistory('${rose.id}')">📜 История</button>
                </div>
            </div>
        </div>
    `).join('');
}

function showCare(roseId) {
    // Здесь можно реализовать показ деталей ухода
    tg.showAlert('🪴 Функция ухода будет реализована позже');
}

function showHistory(roseId) {
    // Здесь можно реализовать показ истории
    tg.showAlert('📜 Функция истории будет реализована позже');
}

function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

// Глобальные функции для доступа из HTML
window.showCare = showCare;
window.showHistory = showHistory;

// Загрузка избранного при открытии
document.addEventListener('DOMContentLoaded', function() {
    // Получаем ID чата из Telegram Web App
    const tg = window.Telegram.WebApp;
    tg.expand();
    
    if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
        const chatId = tg.initDataUnsafe.user.id;
        loadFavorites(chatId);
        
        // Обработчик кнопки обновления
        document.getElementById('refreshBtn').addEventListener('click', function() {
            loadFavorites(chatId);
        });
    } else {
        // Если не удалось получить из initData, попробуем из URL
        const urlParams = new URLSearchParams(window.location.search);
        const chatId = urlParams.get('chat_id');
        if (chatId) {
            loadFavorites(chatId);
        } else {
            document.getElementById('favoritesList').innerHTML = 
                '<div class="error">Не удалось получить данные пользователя</div>';
        }
    }
});
