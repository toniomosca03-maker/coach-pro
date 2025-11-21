// 🏆 COACH MOTIVAZIONALE PRO - VERSIONE 10/10
// Bot Telegram con AI, Gamification, Database e Funzionalità Avanzate

const TelegramBot = require('node-telegram-bot-api');
const Database = require('better-sqlite3');
const cron = require('node-cron');
const { ChartJSNodeCanvas } = require('chartjs-node-canvas');
const axios = require('axios');

// ============================================
// CONFIGURAZIONE
// ============================================

const CONFIG = {
    TELEGRAM_TOKEN: process.env.TELEGRAM_TOKEN || 'IL_TUO_TOKEN_BOT',
    CLAUDE_API_KEY: process.env.CLAUDE_API_KEY || '', // Opzionale - lascia vuoto se non hai
    USE_AI: process.env.CLAUDE_API_KEY ? true : false
};

// ============================================
// INIZIALIZZAZIONE DATABASE
// ============================================

const db = new Database('coach_pro.db');

// Crea tabelle
db.exec(`
    CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        created_at INTEGER,
        last_interaction INTEGER,
        total_points INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        streak_days INTEGER DEFAULT 0,
        last_activity_date TEXT,
        reminder_time TEXT DEFAULT '09:00',
        reminder_enabled INTEGER DEFAULT 1,
        onboarding_completed INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        title TEXT,
        description TEXT,
        category TEXT,
        progress INTEGER DEFAULT 0,
        target_value INTEGER DEFAULT 100,
        created_at INTEGER,
        deadline TEXT,
        completed INTEGER DEFAULT 0,
        completed_at INTEGER,
        FOREIGN KEY (chat_id) REFERENCES users(chat_id)
    );

    CREATE TABLE IF NOT EXISTS progress_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        goal_id INTEGER,
        chat_id INTEGER,
        old_progress INTEGER,
        new_progress INTEGER,
        change_value INTEGER,
        timestamp INTEGER,
        FOREIGN KEY (goal_id) REFERENCES goals(id),
        FOREIGN KEY (chat_id) REFERENCES users(chat_id)
    );

    CREATE TABLE IF NOT EXISTS badges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        badge_type TEXT,
        earned_at INTEGER,
        FOREIGN KEY (chat_id) REFERENCES users(chat_id)
    );

    CREATE TABLE IF NOT EXISTS ai_conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        role TEXT,
        content TEXT,
        timestamp INTEGER,
        FOREIGN KEY (chat_id) REFERENCES users(chat_id)
    );
`);

// ============================================
// BOT TELEGRAM
// ============================================

const bot = new TelegramBot(CONFIG.TELEGRAM_TOKEN, { polling: true });
console.log('🤖 Coach Pro avviato! Bot online...');

// ============================================
// SISTEMA GAMIFICATION
// ============================================

const LEVELS = [
    { level: 1, name: '🌱 Principiante', points: 0 },
    { level: 2, name: '🔰 Apprendista', points: 100 },
    { level: 3, name: '⚡ Motivato', points: 300 },
    { level: 4, name: '💪 Determinato', points: 600 },
    { level: 5, name: '🔥 Guerriero', points: 1000 },
    { level: 6, name: '🏆 Campione', points: 1500 },
    { level: 7, name: '👑 Maestro', points: 2500 },
    { level: 8, name: '⭐ Leggenda', points: 4000 },
    { level: 9, name: '💎 Diamante', points: 6000 },
    { level: 10, name: '🚀 Immortale', points: 10000 }
];

const BADGE_TYPES = {
    FIRST_GOAL: { emoji: '🎯', name: 'Primo Obiettivo', description: 'Hai creato il tuo primo obiettivo!' },
    FIRST_COMPLETE: { emoji: '🏆', name: 'Prima Vittoria', description: 'Hai completato il tuo primo obiettivo!' },
    WEEK_STREAK: { emoji: '🔥', name: 'Settimana di Fuoco', description: '7 giorni di streak!' },
    MONTH_STREAK: { emoji: '💪', name: 'Mese Perfetto', description: '30 giorni di streak!' },
    FIVE_GOALS: { emoji: '⭐', name: 'Ambizioso', description: '5 obiettivi completati!' },
    TEN_GOALS: { emoji: '💎', name: 'Inarrestabile', description: '10 obiettivi completati!' },
    LEVEL_5: { emoji: '🔥', name: 'Guerriero Livello 5', description: 'Hai raggiunto il livello 5!' },
    LEVEL_10: { emoji: '👑', name: 'Immortale', description: 'Livello massimo raggiunto!' },
    EARLY_BIRD: { emoji: '🌅', name: 'Mattiniero', description: 'Attivo prima delle 7:00!' },
    NIGHT_OWL: { emoji: '🦉', name: 'Gufo Notturno', description: 'Attivo dopo le 23:00!' }
};

// ============================================
// FUNZIONI UTILITY
// ============================================

function getOrCreateUser(chatId, userData = {}) {
    let user = db.prepare('SELECT * FROM users WHERE chat_id = ?').get(chatId);
    
    if (!user) {
        db.prepare(`
            INSERT INTO users (chat_id, username, first_name, created_at, last_interaction)
            VALUES (?, ?, ?, ?, ?)
        `).run(chatId, userData.username || '', userData.first_name || '', Date.now(), Date.now());
        
        user = db.prepare('SELECT * FROM users WHERE chat_id = ?').get(chatId);
    }
    
    return user;
}

function updateUserActivity(chatId) {
    const now = Date.now();
    const today = new Date().toDateString();
    
    const user = db.prepare('SELECT * FROM users WHERE chat_id = ?').get(chatId);
    
    if (user) {
        const lastActivityDate = user.last_activity_date;
        const yesterday = new Date(Date.now() - 86400000).toDateString();
        
        let newStreak = user.streak_days;
        
        if (lastActivityDate !== today) {
            if (lastActivityDate === yesterday) {
                newStreak += 1;
                checkStreakBadges(chatId, newStreak);
            } else if (lastActivityDate !== today) {
                newStreak = 1;
            }
        }
        
        db.prepare(`
            UPDATE users 
            SET last_interaction = ?, last_activity_date = ?, streak_days = ?
            WHERE chat_id = ?
        `).run(now, today, newStreak, chatId);
        
        // Badge mattiniero/gufo notturno
        const hour = new Date().getHours();
        if (hour < 7) awardBadge(chatId, 'EARLY_BIRD');
        if (hour >= 23) awardBadge(chatId, 'NIGHT_OWL');
    }
}

function addPoints(chatId, points, reason = '') {
    const user = db.prepare('SELECT * FROM users WHERE chat_id = ?').get(chatId);
    
    if (user) {
        const newPoints = user.total_points + points;
        const oldLevel = user.level;
        const newLevel = calculateLevel(newPoints);
        
        db.prepare('UPDATE users SET total_points = ?, level = ? WHERE chat_id = ?')
            .run(newPoints, newLevel, chatId);
        
        if (newLevel > oldLevel) {
            sendLevelUpMessage(chatId, newLevel);
            if (newLevel === 5) awardBadge(chatId, 'LEVEL_5');
            if (newLevel === 10) awardBadge(chatId, 'LEVEL_10');
        }
        
        if (points > 0 && reason) {
            bot.sendMessage(chatId, `⭐ +${points} punti! ${reason}`);
        }
    }
}

function calculateLevel(points) {
    for (let i = LEVELS.length - 1; i >= 0; i--) {
        if (points >= LEVELS[i].points) {
            return LEVELS[i].level;
        }
    }
    return 1;
}

function getLevelInfo(level) {
    return LEVELS.find(l => l.level === level) || LEVELS[0];
}

function awardBadge(chatId, badgeType) {
    const existing = db.prepare('SELECT * FROM badges WHERE chat_id = ? AND badge_type = ?')
        .get(chatId, badgeType);
    
    if (!existing && BADGE_TYPES[badgeType]) {
        db.prepare('INSERT INTO badges (chat_id, badge_type, earned_at) VALUES (?, ?, ?)')
            .run(chatId, badgeType, Date.now());
        
        const badge = BADGE_TYPES[badgeType];
        bot.sendMessage(chatId, 
            `🎉 *NUOVO BADGE SBLOCCATO!*\n\n` +
            `${badge.emoji} *${badge.name}*\n` +
            `${badge.description}\n\n` +
            `Continua così! 💪`,
            { parse_mode: 'Markdown' }
        );
    }
}

function checkStreakBadges(chatId, streak) {
    if (streak === 7) awardBadge(chatId, 'WEEK_STREAK');
    if (streak === 30) awardBadge(chatId, 'MONTH_STREAK');
}

function sendLevelUpMessage(chatId, newLevel) {
    const levelInfo = getLevelInfo(newLevel);
    bot.sendMessage(chatId,
        `🎉🎉🎉 *LEVEL UP!* 🎉🎉🎉\n\n` +
        `Sei salito al livello ${newLevel}!\n` +
        `${levelInfo.name}\n\n` +
        `Continua a migliorare! 🚀`,
        { parse_mode: 'Markdown' }
    );
}

// ============================================
// FUNZIONI AI
// ============================================

async function getAIResponse(chatId, message) {
    if (!CONFIG.USE_AI || !CONFIG.CLAUDE_API_KEY) {
        return getSmartResponse(message, chatId);
    }
    
    try {
        // Ottieni contesto utente
        const user = db.prepare('SELECT * FROM users WHERE chat_id = ?').get(chatId);
        const goals = db.prepare('SELECT * FROM goals WHERE chat_id = ? AND completed = 0').all(chatId);
        const recentHistory = db.prepare(
            'SELECT * FROM ai_conversations WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 6'
        ).all(chatId);
        
        const context = `Sei un coach motivazionale entusiasta e di supporto.
User info: ${user.first_name}, Livello ${user.level}, Streak ${user.streak_days} giorni.
Obiettivi attivi: ${goals.map(g => `${g.title} (${g.progress}%)`).join(', ')}.
Fornisci risposte brevi (max 2-3 frasi), motivanti e pratiche in italiano.`;
        
        const messages = [
            ...recentHistory.reverse().map(h => ({ role: h.role, content: h.content })),
            { role: 'user', content: message }
        ];
        
        const response = await axios.post(
            'https://api.anthropic.com/v1/messages',
            {
                model: 'claude-sonnet-4-20250514',
                max_tokens: 300,
                system: context,
                messages: messages
            },
            {
                headers: {
                    'Content-Type': 'application/json',
                    'x-api-key': CONFIG.CLAUDE_API_KEY,
                    'anthropic-version': '2023-06-01'
                }
            }
        );
        
        const aiResponse = response.data.content[0].text;
        
        // Salva conversazione
        db.prepare('INSERT INTO ai_conversations (chat_id, role, content, timestamp) VALUES (?, ?, ?, ?)')
            .run(chatId, 'user', message, Date.now());
        db.prepare('INSERT INTO ai_conversations (chat_id, role, content, timestamp) VALUES (?, ?, ?, ?)')
            .run(chatId, 'assistant', aiResponse, Date.now());
        
        return aiResponse;
        
    } catch (error) {
        console.error('Errore AI:', error.message);
        return getSmartResponse(message, chatId);
    }
}

function getSmartResponse(message, chatId) {
    const lowerMsg = message.toLowerCase();
    const user = db.prepare('SELECT * FROM users WHERE chat_id = ?').get(chatId);
    const name = user.first_name || 'amico';
    
    const responses = {
        demotivato: [
            `${name}, capisco come ti senti 💙. Anche i campioni hanno giornate difficili. Ricorda perché hai iniziato!`,
            `Hey ${name}, è normale sentirsi così! Prenditi un momento, respira. Domani è un nuovo giorno! 🌟`,
            `${name}, ogni grande traguardo ha momenti difficili. Questa è solo una curva, non la fine! 💪`
        ],
        stanco: [
            `Il riposo fa parte del processo, ${name}! 😌 Prenditi cura di te. Domani torni più forte!`,
            `${name}, anche i muscoli crescono nel riposo. Ricarica le batterie! ⚡`,
            `Ascolta il tuo corpo, ${name}. Un giorno di pausa può fare miracoli! 🧘`
        ],
        aiuto: [
            `Sono qui per te, ${name}! 🤗 Quale sfida stai affrontando? Parliamone insieme!`,
            `${name}, conta su di me! 💪 Dimmi cosa ti preoccupa e troviamo una soluzione!`,
            `Ehi ${name}, i coach sono fatti per questo! Raccontami tutto 🎯`
        ],
        felice: [
            `Fantastico, ${name}! 🎉 L'energia positiva è contagiosa! Continua così!`,
            `Questo è lo spirito, ${name}! 🌟 Cavalca quest'onda di entusiasmo!`,
            `${name}, la tua energia è potente! 🔥 Usa questa motivazione per spingere ancora!`
        ]
    };
    
    if (lowerMsg.includes('demotivato') || lowerMsg.includes('triste') || lowerMsg.includes('giù')) {
        return responses.demotivato[Math.floor(Math.random() * responses.demotivato.length)];
    }
    if (lowerMsg.includes('stanco') || lowerMsg.includes('fatica') || lowerMsg.includes('esausto')) {
        return responses.stanco[Math.floor(Math.random() * responses.stanco.length)];
    }
    if (lowerMsg.includes('aiuto') || lowerMsg.includes('help') || lowerMsg.includes('problema')) {
        return responses.aiuto[Math.floor(Math.random() * responses.aiuto.length)];
    }
    if (lowerMsg.includes('felice') || lowerMsg.includes('bene') || lowerMsg.includes('grande')) {
        return responses.felice[Math.floor(Math.random() * responses.felice.length)];
    }
    
    return `${name}, ti ascolto! 👂 Come posso aiutarti oggi con i tuoi obiettivi? 🎯`;
}

// ============================================
// GRAFICI
// ============================================

async function generateProgressChart(chatId) {
    const goals = db.prepare('SELECT * FROM goals WHERE chat_id = ? ORDER BY created_at DESC LIMIT 5').all(chatId);
    
    if (goals.length === 0) {
        return null;
    }
    
    const width = 800;
    const height = 400;
    const chartJSNodeCanvas = new ChartJSNodeCanvas({ width, height });
    
    const configuration = {
        type: 'bar',
        data: {
            labels: goals.map(g => g.title.substring(0, 20) + '...'),
            datasets: [{
                label: 'Progresso %',
                data: goals.map(g => g.progress),
                backgroundColor: [
                    'rgba(255, 99, 132, 0.7)',
                    'rgba(54, 162, 235, 0.7)',
                    'rgba(255, 206, 86, 0.7)',
                    'rgba(75, 192, 192, 0.7)',
                    'rgba(153, 102, 255, 0.7)'
                ]
            }]
        },
        options: {
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100
                }
            },
            plugins: {
                title: {
                    display: true,
                    text: 'I Tuoi Progressi',
                    font: { size: 20 }
                }
            }
        }
    };
    
    return await chartJSNodeCanvas.renderToBuffer(configuration);
}

// ============================================
// COMANDI BOT
// ============================================

// /start - Onboarding
bot.onText(/\/start/, async (msg) => {
    const chatId = msg.chat.id;
    const user = getOrCreateUser(chatId, msg.from);
    updateUserActivity(chatId);
    
    if (!user.onboarding_completed) {
        await bot.sendMessage(chatId,
            `🎉 *Benvenuto nel Coach Motivazionale PRO!* 💪\n\n` +
            `Ciao ${msg.from.first_name}! Sono qui per trasformare i tuoi sogni in realtà!\n\n` +
            `✨ Con me avrai:\n` +
            `• 🎯 Sistema di obiettivi intelligente\n` +
            `• 🏆 Gamification con punti e badge\n` +
            `• 📊 Grafici dei tuoi progressi\n` +
            `• 🤖 AI Coach personale\n` +
            `• 🔥 Sistema di streak per restare motivato\n\n` +
            `Pronto a iniziare questo viaggio insieme? 🚀`,
            { parse_mode: 'Markdown' }
        );
        
        setTimeout(() => {
            bot.sendMessage(chatId,
                `💡 *In quale area vuoi migliorare?*\n\n` +
                `Seleziona la categoria del tuo primo obiettivo:`,
                {
                    parse_mode: 'Markdown',
                    reply_markup: {
                        inline_keyboard: [
                            [
                                { text: '💪 Fitness', callback_data: 'cat_fitness' },
                                { text: '💼 Carriera', callback_data: 'cat_carriera' }
                            ],
                            [
                                { text: '💰 Finanze', callback_data: 'cat_finanze' },
                                { text: '📚 Studio', callback_data: 'cat_studio' }
                            ],
                            [
                                { text: '❤️ Relazioni', callback_data: 'cat_relazioni' },
                                { text: '🎨 Hobby', callback_data: 'cat_hobby' }
                            ],
                            [
                                { text: '🔍 Altro', callback_data: 'cat_altro' }
                            ]
                        ]
                    }
                }
            );
        }, 2000);
        
    } else {
        const stats = getUserStats(chatId);
        bot.sendMessage(chatId,
            `👋 Bentornato, ${msg.from.first_name}!\n\n` +
            `📊 *Il tuo stato:*\n` +
            `${getLevelInfo(user.level).name}\n` +
            `🔥 Streak: ${user.streak_days} giorni\n` +
            `⭐ Punti: ${user.total_points}\n` +
            `🎯 Obiettivi attivi: ${stats.activeGoals}\n\n` +
            `Usa /aiuto per vedere tutti i comandi! 💪`,
            { parse_mode: 'Markdown' }
        );
    }
});

// Gestione selezione categoria
bot.on('callback_query', async (query) => {
    const chatId = query.message.chat.id;
    const data = query.data;
    
    if (data.startsWith('cat_')) {
        const category = data.replace('cat_', '');
        
        // Salva categoria temporanea
        db.prepare('UPDATE users SET onboarding_completed = 1 WHERE chat_id = ?').run(chatId);
        
        bot.answerCallbackQuery(query.id);
        bot.sendMessage(chatId,
            `Perfetto! Hai scelto: *${category}* 🎯\n\n` +
            `Ora scrivi il tuo obiettivo specifico.\n\n` +
            `*Esempi:*\n` +
            `• "Perdere 5kg in 2 mesi"\n` +
            `• "Correre 5km senza fermarmi"\n` +
            `• "Risparmiare 1000€ in 3 mesi"\n\n` +
            `Il tuo obiettivo 👇`,
            { parse_mode: 'Markdown' }
        );
        
        // Imposta stato per catturare prossimo messaggio
        const userState = db.prepare('SELECT * FROM users WHERE chat_id = ?').get(chatId);
        // Implementazione stato utente...
        
        awardBadge(chatId, 'FIRST_GOAL');
    }
});

// /nuovo - Nuovo obiettivo
bot.onText(/\/nuovo/, (msg) => {
    const chatId = msg.chat.id;
    updateUserActivity(chatId);
    
    bot.sendMessage(chatId,
        `✨ *Nuovo obiettivo!*\n\n` +
        `Descrivi il tuo obiettivo in modo specifico.\n\n` +
        `*Suggerimenti per un buon obiettivo:*\n` +
        `• Specifico: "Correre 5km" non "Fare sport"\n` +
        `• Misurabile: Includi numeri\n` +
        `• Realizzabile: Sfidante ma possibile\n\n` +
        `Scrivi il tuo obiettivo 👇`,
        { parse_mode: 'Markdown' }
    );
});

// /obiettivi - Lista obiettivi
bot.onText(/\/obiettivi/, async (msg) => {
    const chatId = msg.chat.id;
    updateUserActivity(chatId);
    
    const goals = db.prepare('SELECT * FROM goals WHERE chat_id = ? ORDER BY completed ASC, created_at DESC')
        .all(chatId);
    
    if (goals.length === 0) {
        bot.sendMessage(chatId,
            `📋 *Nessun obiettivo ancora!*\n\n` +
            `Usa /nuovo per creare il tuo primo obiettivo! 🎯`,
            { parse_mode: 'Markdown' }
        );
        return;
    }
    
    let message = `📋 *I TUOI OBIETTIVI*\n\n`;
    
    const active = goals.filter(g => !g.completed);
    const completed = goals.filter(g => g.completed);
    
    if (active.length > 0) {
        message += `🎯 *Attivi:*\n\n`;
        active.forEach((goal, idx) => {
            const progressBar = '█'.repeat(Math.floor(goal.progress / 10)) + 
                              '░'.repeat(10 - Math.floor(goal.progress / 10));
            message += `${idx + 1}. *${goal.title}*\n`;
            message += `   ${progressBar} ${goal.progress}%\n`;
            if (goal.deadline) message += `   📅 ${goal.deadline}\n`;
            message += `\n`;
        });
    }
    
    if (completed.length > 0) {
        message += `\n✅ *Completati: ${completed.length}*\n`;
    }
    
    bot.sendMessage(chatId, message, {
        parse_mode: 'Markdown',
        reply_markup: {
            inline_keyboard: [
                [
                    { text: '📊 Vedi Grafici', callback_data: 'show_charts' },
                    { text: '➕ Nuovo Obiettivo', callback_data: 'new_goal' }
                ]
            ]
        }
    });
});

// /progresso - Aggiorna progresso
bot.onText(/\/progresso/, (msg) => {
    const chatId = msg.chat.id;
    updateUserActivity(chatId);
    
    const goals = db.prepare('SELECT * FROM goals WHERE chat_id = ? AND completed = 0').all(chatId);
    
    if (goals.length === 0) {
        bot.sendMessage(chatId, `❌ Non hai obiettivi attivi!\n\nUsa /nuovo per crearne uno! 🎯`);
        return;
    }
    
    let message = `📊 *Aggiorna Progresso*\n\n`;
    goals.forEach((goal, idx) => {
        message += `${idx + 1}. ${goal.title} (${goal.progress}%)\n`;
    });
    message += `\n💡 Scrivi: *numero +valore*\n`;
    message += `Esempio: \`1 +10\` o \`2 +25\``;
    
    bot.sendMessage(chatId, message, { parse_mode: 'Markdown' });
});

// /stats - Statistiche complete
bot.onText(/\/stats/, async (msg) => {
    const chatId = msg.chat.id;
    updateUserActivity(chatId);
    
    const user = db.prepare('SELECT * FROM users WHERE chat_id = ?').get(chatId);
    const stats = getUserStats(chatId);
    const badges = db.prepare('SELECT * FROM badges WHERE chat_id = ?').all(chatId);
    const levelInfo = getLevelInfo(user.level);
    const nextLevelInfo = getLevelInfo(user.level + 1);
    
    const pointsToNextLevel = nextLevelInfo ? nextLevelInfo.points - user.total_points : 0;
    
    let message = `📊 *LE TUE STATISTICHE*\n\n`;
    message += `👤 *Profilo*\n`;
    message += `${levelInfo.name}\n`;
    message += `⭐ ${user.total_points} punti`;
    if (nextLevelInfo) {
        message += ` (${pointsToNextLevel} al prossimo livello)`;
    }
    message += `\n🔥 Streak: ${user.streak_days} giorni\n\n`;
    
    message += `🎯 *Obiettivi*\n`;
    message += `Attivi: ${stats.activeGoals}\n`;
    message += `Completati: ${stats.completedGoals}\n`;
    message += `Progresso medio: ${stats.avgProgress}%\n\n`;
    
    message += `🏆 *Badge (${badges.length})*\n`;
    if (badges.length > 0) {
        badges.slice(0, 5).forEach(badge => {
            const badgeInfo = BADGE_TYPES[badge.badge_type];
            if (badgeInfo) {
                message += `${badgeInfo.emoji} ${badgeInfo.name}\n`;
            }
        });
        if (badges.length > 5) {
            message += `...e altri ${badges.length - 5}\n`;
        }
    } else {
        message += `Nessun badge ancora. Inizia a completare obiettivi! 💪\n`;
    }
    
    bot.sendMessage(chatId, message, {
        parse_mode: 'Markdown',
        reply_markup: {
            inline_keyboard: [
                [{ text: '📊 Vedi Grafici', callback_data: 'show_charts' }]
            ]
        }
    });
});

// /grafici - Mostra grafici
bot.onText(/\/grafici/, async (msg) => {
    const chatId = msg.chat.id;
    updateUserActivity(chatId);
    
    try {
        const chartBuffer = await generateProgressChart(chatId);
        
        if (chartBuffer) {
            await bot.sendPhoto(chatId, chartBuffer, {
                caption: '📊 *I Tuoi Progressi*\n\nContinua così! 💪',
                parse_mode: 'Markdown'
            });
            addPoints(chatId, 5, 'Hai controllato i tuoi progressi!');
        } else {
            bot.sendMessage(chatId, '❌ Aggiungi alcuni obiettivi prima di vedere i grafici!');
        }
    } catch (error) {
        console.error('Errore grafici:', error);
        bot.sendMessage(chatId, '❌ Errore nella generazione dei grafici. Riprova!');
    }
});

// /motivazione - Dose di motivazione
bot.onText(/\/motivazione/, (msg) => {
    const chatId = msg.chat.id;
    updateUserActivity(chatId);
    
    const quotes = [
        '💪 Sei più forte di quanto pensi! Ogni sfida è un\'opportunità!',
        '🌟 Il successo è la somma di piccoli sforzi ripetuti ogni giorno!',
        '🔥 La disciplina batte il talento quando il talento non si allena!',
        '🎯 Non contare i giorni. Fai che i giorni contino!',
        '⚡ Il momento migliore per iniziare era ieri. Il secondo migliore è ORA!',
        '🚀 Credi in te stesso e sarai inarrestabile!',
        '💎 I diamanti si formano sotto pressione. Tu sei un diamante in formazione!',
        '🏆 Il dolore è temporaneo. Il successo è permanente!',
        '✨ Ogni esperto è stato una volta un principiante che non si è arreso!',
        '👑 Sei il creatore del tuo destino. Agisci come tale!'
    ];
    
    const quote = quotes[Math.floor(Math.random() * quotes.length)];
    bot.sendMessage(chatId, quote);
    addPoints(chatId, 2);
});

// /aiuto - Lista comandi
bot.onText(/\/aiuto/, (msg) => {
    const chatId = msg.chat.id;
    
    const helpMessage = `
🤖 *COMANDI DISPONIBILI*

📋 *Gestione Obiettivi:*
/nuovo - Crea un nuovo obiettivo
/obiettivi - Vedi tutti gli obiettivi
/progresso - Aggiorna i progressi

📊 *Statistiche:*
/stats - Le tue statistiche complete
/grafici - Grafici dei progressi
/badge - Vedi tutti i tuoi badge

⚙️ *Impostazioni:*
/promemoria - Imposta orario promemoria
/profilo - Vedi il tuo profilo

💬 *Altro:*
/motivazione - Dose di motivazione
/aiuto - Mostra questo messaggio

💬 *Chat Libera:*
Scrivi liberamente per parlare con il tuo AI Coach!

Sono qui per te 24/7! 🌟
    `;
    
    bot.sendMessage(chatId, helpMessage, { parse_mode: 'Markdown' });
});

// /promemoria - Imposta promemoria
bot.onText(/\/promemoria/, (msg) => {
    const chatId = msg.chat.id;
    
    bot.sendMessage(chatId,
        `⏰ *Imposta il tuo promemoria giornaliero*\n\n` +
        `Attualmente: 09:00\n\n` +
        `Scrivi l'orario desiderato (formato 24h):\n` +
        `Esempio: \`08:30\` o \`14:00\``,
        { parse_mode: 'Markdown' }
    );
});

// /badge - Mostra badge
bot.onText(/\/badge/, (msg) => {
    const chatId = msg.chat.id;
    updateUserActivity(chatId);
    
    const badges = db.prepare('SELECT * FROM badges WHERE chat_id = ? ORDER BY earned_at DESC').all(chatId);
    
    if (badges.length === 0) {
        bot.sendMessage(chatId,
            `🏆 *BADGE*\n\n` +
            `Non hai ancora badge!\n\n` +
            `Completa obiettivi e mantieni lo streak per sbloccare badge! 💪`,
            { parse_mode: 'Markdown' }
        );
        return;
    }
    
    let message = `🏆 *I TUOI BADGE (${badges.length})*\n\n`;
    
    badges.forEach(badge => {
        const badgeInfo = BADGE_TYPES[badge.badge_type];
        if (badgeInfo) {
            const date = new Date(badge.earned_at).toLocaleDateString('it-IT');
            message += `${badgeInfo.emoji} *${badgeInfo.name}*\n`;
            message += `   ${badgeInfo.description}\n`;
            message += `   Ottenuto: ${date}\n\n`;
        }
    });
    
    bot.sendMessage(chatId, message, { parse_mode: 'Markdown' });
});

// Gestione messaggi normali
bot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    const text = msg.text;
    
    // Ignora comandi
    if (text.startsWith('/')) return;
    
    updateUserActivity(chatId);
    
    // Controlla se è aggiornamento progresso (formato: "1 +10")
    const progressMatch = text.match(/^(\d+)\s*([+-]\d+)$/);
    if (progressMatch) {
        const goalIndex = parseInt(progressMatch[1]) - 1;
        const change = parseInt(progressMatch[2]);
        
        const goals = db.prepare('SELECT * FROM goals WHERE chat_id = ? AND completed = 0').all(chatId);
        
        if (goalIndex >= 0 && goalIndex < goals.length) {
            const goal = goals[goalIndex];
            const oldProgress = goal.progress;
            const newProgress = Math.max(0, Math.min(100, oldProgress + change));
            
            db.prepare('UPDATE goals SET progress = ? WHERE id = ?').run(newProgress, goal.id);
            
            // Salva storico
            db.prepare(
                'INSERT INTO progress_history (goal_id, chat_id, old_progress, new_progress, change_value, timestamp) VALUES (?, ?, ?, ?, ?, ?)'
            ).run(goal.id, chatId, oldProgress, newProgress, change, Date.now());
            
            // Punti
            if (change > 0) {
                addPoints(chatId, Math.floor(change / 5), 'Progresso aggiornato!');
            }
            
            const progressBar = '█'.repeat(Math.floor(newProgress / 10)) + 
                              '░'.repeat(10 - Math.floor(newProgress / 10));
            
            let response = `✅ *Aggiornato!*\n\n`;
            response += `${goal.title}\n`;
            response += `${progressBar} ${newProgress}%\n\n`;
            
            if (newProgress >= 100) {
                db.prepare('UPDATE goals SET completed = 1, completed_at = ? WHERE id = ?')
                    .run(Date.now(), goal.id);
                
                response += `🎉🎉🎉 *OBIETTIVO COMPLETATO!* 🎉🎉🎉\n\n`;
                response += `Sono ORGOGLIOSO di te! 💪🌟\n`;
                response += `Hai dimostrato vera determinazione!\n\n`;
                
                addPoints(chatId, 100, 'Obiettivo completato! 🏆');
                awardBadge(chatId, 'FIRST_COMPLETE');
                
                // Controlla badge multipli completamenti
                const completedCount = db.prepare('SELECT COUNT(*) as count FROM goals WHERE chat_id = ? AND completed = 1')
                    .get(chatId).count;
                if (completedCount === 5) awardBadge(chatId, 'FIVE_GOALS');
                if (completedCount === 10) awardBadge(chatId, 'TEN_GOALS');
                
            } else if (change > 0) {
                response += `💪 Grande! Stai facendo progressi reali!\nContinua così! 🔥`;
            }
            
            bot.sendMessage(chatId, response, { parse_mode: 'Markdown' });
            return;
        }
    }
    
    // Controlla se è impostazione orario promemoria
    const timeMatch = text.match(/^(\d{1,2}):(\d{2})$/);
    if (timeMatch) {
        const hour = parseInt(timeMatch[1]);
        const minute = parseInt(timeMatch[2]);
        
        if (hour >= 0 && hour < 24 && minute >= 0 && minute < 60) {
            db.prepare('UPDATE users SET reminder_time = ? WHERE chat_id = ?')
                .run(`${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`, chatId);
            
            bot.sendMessage(chatId, 
                `✅ Promemoria impostato alle ${hour}:${minute.toString().padStart(2, '0')}!\n\n` +
                `Ti ricorderò ogni giorno di lavorare sui tuoi obiettivi! ⏰`
            );
            return;
        }
    }
    
    // Controlla se è nuovo obiettivo (messaggio lungo)
    if (text.length > 10 && text.length < 200 && !text.includes('?')) {
        // Probabilmente sta creando un obiettivo
        const newGoal = {
            chat_id: chatId,
            title: text,
            description: '',
            category: 'generale',
            progress: 0,
            created_at: Date.now(),
            deadline: null,
            completed: 0
        };
        
        db.prepare(
            'INSERT INTO goals (chat_id, title, description, category, progress, created_at, deadline, completed) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
        ).run(newGoal.chat_id, newGoal.title, newGoal.description, newGoal.category, newGoal.progress, newGoal.created_at, newGoal.deadline, newGoal.completed);
        
        addPoints(chatId, 20, 'Nuovo obiettivo creato!');
        
        const goalCount = db.prepare('SELECT COUNT(*) as count FROM goals WHERE chat_id = ?').get(chatId).count;
        if (goalCount === 1) awardBadge(chatId, 'FIRST_GOAL');
        
        bot.sendMessage(chatId,
            `✅ *Perfetto! Obiettivo aggiunto:*\n\n` +
            `"${text}"\n\n` +
            `🎯 Ora inizia a lavorarci!\n` +
            `Usa /progresso per aggiornare i tuoi progressi! 💪`,
            { parse_mode: 'Markdown' }
        );
        return;
    }
    
    // Chat libera con AI
    const aiResponse = await getAIResponse(chatId, text);
    bot.sendMessage(chatId, aiResponse);
    addPoints(chatId, 1);
});

// ============================================
// FUNZIONI STATISTICHE
// ============================================

function getUserStats(chatId) {
    const goals = db.prepare('SELECT * FROM goals WHERE chat_id = ?').all(chatId);
    const activeGoals = goals.filter(g => !g.completed).length;
    const completedGoals = goals.filter(g => g.completed).length;
    const avgProgress = goals.length > 0 
        ? Math.round(goals.reduce((sum, g) => sum + g.progress, 0) / goals.length)
        : 0;
    
    return { activeGoals, completedGoals, avgProgress };
}

// ============================================
// SISTEMA PROMEMORIA AUTOMATICO
// ============================================

// Promemoria giornaliero personalizzato
cron.schedule('*/30 * * * *', () => {
    // Controlla ogni 30 minuti
    const now = new Date();
    const currentTime = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
    
    const users = db.prepare('SELECT * FROM users WHERE reminder_enabled = 1').all();
    
    users.forEach(user => {
        const reminderTime = user.reminder_time || '09:00';
        const [reminderHour, reminderMinute] = reminderTime.split(':').map(Number);
        const [currentHour, currentMinute] = currentTime.split(':').map(Number);
        
        // Controlla se è l'ora giusta (con margine di 30 minuti)
        if (Math.abs(currentHour - reminderHour) === 0 && Math.abs(currentMinute - reminderMinute) < 30) {
            const goals = db.prepare('SELECT * FROM goals WHERE chat_id = ? AND completed = 0').all(user.chat_id);
            
            if (goals.length > 0) {
                bot.sendMessage(user.chat_id,
                    `⏰ *Promemoria giornaliero!*\n\n` +
                    `Buongiorno! 🌅\n\n` +
                    `Hai ${goals.length} obiettivi attivi.\n` +
                    `🔥 Streak attuale: ${user.streak_days} giorni\n\n` +
                    `Cosa farai oggi per avvicinarti ai tuoi traguardi?\n\n` +
                    `Ricorda: piccoli passi ogni giorno! 💪`,
                    { parse_mode: 'Markdown' }
                );
            }
        }
    });
});

// Coaching proattivo - Controlla utenti inattivi
cron.schedule('0 20 * * *', () => {
    const threeDaysAgo = Date.now() - (3 * 24 * 60 * 60 * 1000);
    const users = db.prepare('SELECT * FROM users WHERE last_interaction < ?').all(threeDaysAgo);
    
    users.forEach(user => {
        const goals = db.prepare('SELECT * FROM goals WHERE chat_id = ? AND completed = 0').all(user.chat_id);
        
        if (goals.length > 0) {
            bot.sendMessage(user.chat_id,
                `👋 Ehi! Ti manco? 😊\n\n` +
                `Non ti vedo da qualche giorno!\n` +
                `I tuoi obiettivi ti aspettano! 🎯\n\n` +
                `Tutto ok? Come posso aiutarti? 💙`,
                { parse_mode: 'Markdown' }
            );
        }
    });
});

// Motivazione settimanale (Lunedì mattina)
cron.schedule('0 8 * * 1', () => {
    const users = db.prepare('SELECT * FROM users').all();
    
    users.forEach(user => {
        const stats = getUserStats(user.chat_id);
        
        if (stats.activeGoals > 0) {
            bot.sendMessage(user.chat_id,
                `🌟 *BUON LUNEDÌ!* 🌟\n\n` +
                `Nuova settimana = Nuove opportunità! 💪\n\n` +
                `📊 Il tuo recap:\n` +
                `🎯 ${stats.activeGoals} obiettivi attivi\n` +
                `🔥 Streak: ${user.streak_days} giorni\n` +
                `${getLevelInfo(user.level).name}\n\n` +
                `Cosa realizzerai questa settimana? 🚀\n\n` +
                `Io credo in te! 💙`,
                { parse_mode: 'Markdown' }
            );
        }
    });
});

console.log('✅ Coach Pro completamente configurato!');
console.log('🚀 Bot attivo e pronto a motivare!');
console.log('💡 Funzionalità: Database, AI, Gamification, Grafici, Promemoria personalizzati');


