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

// Функция добавления в избранное
async function addToFavorites(chatId, roseData) {
    try {
        const response = await fetch('/app/favorites/add', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                chat_id: chatId,
                first_name: tg.initDataUnsafe.user.first_name || '',
                username: tg.initDataUnsafe.user.username || '',
                rose: roseData
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            tg.showAlert('✅ Добавлено в избранное!');
            // Обновляем список
            loadFavorites(chatId);
        } else {
            tg.showAlert('❌ Ошибка: ' + (data.error || 'Неизвестная ошибка'));
        }
    } catch (error) {
        console.error('Ошибка:', error);
        tg.showAlert('❌ Ошибка добавления в избранное');
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
window.addToFavorites = addToFavorites;
