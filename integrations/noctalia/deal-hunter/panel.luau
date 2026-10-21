--!nonstrict

-- Layout do painel (de cima para baixo):
--   cabeçalho (status + switch liga/desliga) → adicionar produto → aviso "pausado"
--   → abas Promoções | Watchlist → conteúdo da aba → rodapé (status + Buscar agora)
-- Só usa papéis de cor do matugen (primary, tertiary, on_surface…), nunca hex fixo.

local typedQuery = ""
local typedPrice = ""
local inputSeed = 0
local exclusive = false
local activeTab = "deals"

local desktopNotif = true
local typedToken = ""
local typedChatId = ""
local settingsSynced = false
local settingsSeed = 0

local function sendCmd(action, arg)
    noctalia.state.set("cmd", {
        action = action,
        arg = tostring(arg or ""),
        ts = os.clock(),
    })
end

local function buildCombinedPayload()
    local q = noctalia.string.trim(tostring(typedQuery or ""))
    local p = noctalia.string.trim(tostring(typedPrice or ""))
    if q == "" then
        return ""
    end
    if p ~= "" and not q:find("|", 1, true) then
        return q .. " | " .. p
    end
    return q
end

local function submitProduct()
    local payload = buildCombinedPayload()
    if payload ~= "" then
        sendCmd(exclusive and "set-query" or "add-item", payload)
        typedQuery = ""
        typedPrice = ""
        inputSeed += 1
    end
end

local function truncate(text, maxLen)
    text = tostring(text or "")
    if #text > maxLen then
        return noctalia.string.trim(text:sub(1, maxLen)) .. "…"
    end
    return text
end

local function card(props, children)
    props.padding = props.padding or 10
    props.radius = props.radius or 12
    props.fill = props.fill or "surface_variant/0.4"
    return ui.row(props, children)
end

local function buildHeader(status, running, busy)
    local total = tonumber(status.total_count) or 0
    local activeCount = tonumber(status.active_count) or 0
    local statusText
    if not running then
        statusText = "Pausado"
    elseif total == 0 then
        statusText = "Nenhum produto na watchlist"
    else
        statusText = string.format("Monitorando %d de %d produtos", activeCount, total)
    end

    return ui.row({ gap = 10, align = "center" }, {
        ui.row({ padding = 8, radius = 10, fill = "primary/0.2" }, {
            ui.glyph({ name = running and "tag" or "tag-off", color = running and "primary" or "outline" }),
        }),
        ui.column({ gap = 2, flexGrow = 1 }, {
            ui.label({ text = "Deal Hunter", fontSize = 15, fontWeight = "bold", color = "on_surface" }),
            ui.row({ gap = 6, align = "center" }, {
                ui.label({ text = "●", fontSize = 9, color = running and "primary" or "outline" }),
                ui.label({ text = statusText, fontSize = 12, color = "on_surface_variant" }),
            }),
        }),
        ui.toggle({
            checked = running,
            enabled = not busy,
            onChange = function(_val)
                sendCmd("toggle-service", "")
            end,
        }),
        ui.button({ glyph = "close", variant = "ghost", onClick = "onClosePanel" }),
    })
end

local function buildQuickAdd(busy)
    return ui.column({ gap = 10, padding = 12, radius = 12, fill = "surface_variant/0.4" }, {
        ui.row({ gap = 8, align = "center" }, {
            ui.column({ gap = 4, flexGrow = 2 }, {
                ui.label({ text = "Produto", fontSize = 12, fontWeight = "medium", color = "on_surface_variant" }),
                ui.input({
                    key = "query-input-" .. tostring(inputSeed),
                    value = typedQuery,
                    placeholder = "Ex: Galaxy S24",
                    onChange = "onQueryChange",
                    onSubmit = "onQuerySubmit",
                    enabled = not busy,
                }),
            }),
            ui.column({ gap = 4, flexGrow = 1 }, {
                ui.label({ text = "Até (R$)", fontSize = 12, fontWeight = "medium", color = "on_surface_variant" }),
                ui.input({
                    key = "price-input-" .. tostring(inputSeed),
                    value = typedPrice,
                    placeholder = "2500",
                    onChange = "onPriceChange",
                    onSubmit = "onPriceSubmit",
                    enabled = not busy,
                }),
            }),
            -- rótulo vazio para o botão alinhar com os campos, não com os rótulos
            ui.column({ gap = 4 }, {
                ui.label({ text = " ", fontSize = 12, fontWeight = "medium" }),
                ui.button({
                    glyph = "plus",
                    variant = "primary",
                    enabled = not busy,
                    onClick = "onAddProduct",
                }),
            }),
        }),
        ui.row({ gap = 8, align = "center" }, {
            ui.toggle({ checked = exclusive, onChange = "onExclusiveChange" }),
            ui.label({ text = "Monitorar só este (pausa os outros)", fontSize = 12, color = "on_surface_variant" }),
        }),
    })
end

local function buildPausedNotice(busy)
    return card({ gap = 10, align = "center", fill = "surface_variant/0.6" }, {
        ui.glyph({ name = "power", color = "on_surface_variant" }),
        ui.column({ gap = 2, flexGrow = 1 }, {
            ui.label({ text = "Monitoramento pausado", fontSize = 13, fontWeight = "bold", color = "on_surface" }),
            ui.label({ text = "Sua watchlist continua salva.", fontSize = 12, color = "on_surface_variant" }),
        }),
        ui.button({
            text = "Ligar",
            glyph = "player-play",
            variant = "primary",
            enabled = not busy,
            onClick = "onToggleService",
        }),
    })
end

local function buildTabs(dealCount, itemCount)
    local function tab(id, label, count)
        local selected = activeTab == id
        return ui.column({ flexGrow = 1, align = "center" }, {
            ui.button({
                text = string.format("%s  %d", label, count),
                variant = selected and "secondary" or "ghost",
                onClick = id == "deals" and "onShowDeals" or "onShowWatchlist",
            }),
        })
    end

    return ui.row({ gap = 4, padding = 4, radius = 12, fill = "surface_variant/0.4" }, {
        tab("deals", "Promoções", dealCount),
        tab("watchlist", "Watchlist", itemCount),
    })
end

local function buildDeals(recentDeals)
    local rows = {}
    for _i, deal in ipairs(recentDeals) do
        local dealUrl = tostring(deal.url or "")
        local meta = tostring(deal.store or "Loja")
        if type(deal.ago) == "string" and deal.ago ~= "" then
            meta = meta .. " · " .. deal.ago
        end

        local priceColumn = {
            ui.label({
                text = tostring(deal.price_label or string.format("R$ %.2f", tonumber(deal.price) or 0)),
                fontSize = 15,
                fontWeight = "bold",
                color = "primary",
            }),
        }
        if type(deal.saving) == "string" and deal.saving ~= "" then
            table.insert(priceColumn, ui.row({ padding = 3, radius = 6, fill = "tertiary/0.2" }, {
                ui.label({ text = deal.saving, fontSize = 11, fontWeight = "bold", color = "tertiary" }),
            }))
        end

        table.insert(rows, card({ gap = 10, align = "center" }, {
            ui.column({ gap = 3, flexGrow = 1 }, {
                ui.label({ text = truncate(deal.title or "Oferta", 30), fontSize = 13, fontWeight = "medium", color = "on_surface" }),
                ui.label({ text = meta, fontSize = 11, color = "on_surface_variant" }),
            }),
            ui.column({ gap = 4 }, priceColumn),
            ui.button({
                glyph = "external-link",
                variant = "ghost",
                onClick = function()
                    sendCmd("open-url", dealUrl)
                end,
            }),
        }))
    end

    if #rows == 0 then
        table.insert(rows, ui.column({ gap = 6, align = "center", padding = 20 }, {
            ui.glyph({ name = "tag", color = "on_surface_variant" }),
            ui.label({ text = "Nenhuma promoção por enquanto", fontSize = 13, fontWeight = "bold", color = "on_surface" }),
            ui.label({
                text = "Quando algo cair abaixo do seu alvo, aparece aqui.",
                fontSize = 12,
                color = "on_surface_variant",
            }),
        }))
    end

    return ui.scroll({ flexGrow = 1, gap = 6 }, rows)
end

local function buildWatchlist(items, busy)
    local rows = {}
    for _idx, item in ipairs(items) do
        local isAct = item.active == true
        local itemId = tostring(item.id)
        local priceStr = "até " .. tostring(item.max_price_label or string.format("R$ %.0f", tonumber(item.max_price) or 0))
        local found = tonumber(item.found_count) or 0
        local meta
        if not isAct then
            meta = priceStr .. " · pausado"
        elseif found == 0 then
            meta = priceStr .. " · nenhuma ainda"
        else
            meta = string.format("%s · %d achada%s", priceStr, found, found == 1 and "" or "s")
        end

        table.insert(rows, card({ gap = 10, align = "center", padding = 8 }, {
            ui.toggle({
                checked = isAct,
                enabled = not busy,
                onChange = function(_val)
                    sendCmd("toggle-item", itemId)
                end,
            }),
            ui.column({ gap = 2, flexGrow = 1 }, {
                ui.label({
                    text = truncate(item.query, 24),
                    fontWeight = "bold",
                    color = isAct and "on_surface" or "on_surface_variant",
                }),
                ui.label({ text = meta, fontSize = 11, color = "on_surface_variant" }),
            }),
            ui.button({
                text = "Focar",
                glyph = "target",
                variant = "ghost",
                enabled = not busy,
                onClick = function()
                    sendCmd("select-only", itemId)
                end,
            }),
            ui.button({
                glyph = "trash",
                variant = "ghost",
                enabled = not busy,
                onClick = function()
                    sendCmd("del-item", itemId)
                end,
            }),
        }))
    end

    if #rows == 0 then
        table.insert(rows, ui.column({ gap = 6, align = "center", padding = 20 }, {
            ui.label({ text = "Watchlist vazia", fontSize = 13, fontWeight = "bold", color = "on_surface" }),
            ui.label({ text = "Adicione um produto e um preço-alvo acima.", fontSize = 12, color = "on_surface_variant" }),
        }))
    end

    return ui.scroll({ flexGrow = 1, gap = 6 }, rows)
end

local function buildSettings(busy)
    return ui.scroll({ flexGrow = 1, gap = 8 }, {
        ui.column({ gap = 8, padding = 12, radius = 12, fill = "surface_variant/0.4" }, {
            ui.row({ gap = 8, align = "center", justify = "space_between" }, {
                ui.column({ gap = 2, flexGrow = 1 }, {
                    ui.label({ text = "Notificações no PC", fontSize = 13, fontWeight = "bold", color = "on_surface" }),
                    ui.label({ text = "Alertas clicáveis direto na área de trabalho", fontSize = 11, color = "on_surface_variant" }),
                }),
                ui.toggle({
                    checked = desktopNotif,
                    enabled = not busy,
                    onChange = "onDesktopNotifChange",
                }),
                ui.button({
                    text = "Testar",
                    glyph = "bell",
                    variant = "secondary",
                    enabled = not busy,
                    onClick = "onTestNotify",
                }),
            }),
        }),

        ui.column({ gap = 8, padding = 12, radius = 12, fill = "surface_variant/0.4" }, {
            ui.row({ gap = 8, align = "center", justify = "space_between" }, {
                ui.column({ gap = 2, flexGrow = 1 }, {
                    ui.label({ text = "Telegram (@BotFather)", fontSize = 13, fontWeight = "bold", color = "on_surface" }),
                    ui.label({ text = "Opcional: receba alertas no celular", fontSize = 11, color = "on_surface_variant" }),
                }),
                ui.button({
                    text = "Guia (PT/EN)",
                    glyph = "help",
                    variant = "secondary",
                    onClick = "onOpenHelp",
                }),
            }),
            ui.column({ gap = 4 }, {
                ui.label({ text = "Bot Token (@BotFather)", fontSize = 11, fontWeight = "medium", color = "on_surface_variant" }),
                ui.input({
                    key = "token-input-" .. tostring(settingsSeed),
                    value = typedToken,
                    placeholder = "Ex: 123456:AAHdqTcv...",
                    onChange = "onTokenChange",
                    enabled = not busy,
                }),
            }),
            ui.column({ gap = 4 }, {
                ui.label({ text = "Chat ID (opcional — auto com /start)", fontSize = 11, fontWeight = "medium", color = "on_surface_variant" }),
                ui.input({
                    key = "chatid-input-" .. tostring(settingsSeed),
                    value = typedChatId,
                    placeholder = "Ex: 987654321",
                    onChange = "onChatIdChange",
                    enabled = not busy,
                }),
            }),
            ui.button({
                text = "Salvar ajustes",
                glyph = "check",
                variant = "primary",
                enabled = not busy,
                onClick = "onSaveSettings",
            }),
        }),
    })
end

local function buildCoffeeCard()
    return card({ gap = 8, align = "center", padding = 10, fill = "primary/0.15" }, {
        ui.glyph({ name = "coffee", color = "primary" }),
        ui.column({ gap = 2, flexGrow = 1 }, {
            ui.label({ text = "Gostou? Me compra um café", fontSize = 12, fontWeight = "bold", color = "on_surface" }),
            ui.label({ text = "Apoie o projeto via Pix", fontSize = 11, color = "on_surface_variant" }),
        }),
        ui.button({
            text = "Chave Pix",
            glyph = "copy",
            variant = "secondary",
            onClick = "onCopyPix",
        }),
        ui.button({
            text = "QR Code",
            glyph = "qrcode",
            variant = "ghost",
            onClick = "onOpenPixQr",
        }),
    })
end

local function buildFooter(status, busy)
    local text
    if busy then
        text = "Buscando…"
    elseif type(status.message) == "string" and status.message ~= "" then
        text = status.message
    else
        text = tostring(status.footer or "Pronto")
    end

    return ui.row({ gap = 6, align = "center" }, {
        ui.label({ text = text, fontSize = 11, color = "on_surface_variant", flexGrow = 1 }),
        ui.button({
            text = "Buscar agora",
            glyph = "refresh",
            variant = "secondary",
            enabled = not busy,
            onClick = "onCheckNow",
        }),
        ui.button({
            glyph = "settings",
            variant = activeTab == "settings" and "primary" or "ghost",
            onClick = "onToggleSettings",
        }),
        ui.button({
            glyph = "help",
            variant = "ghost",
            onClick = "onOpenHelp",
        }),
    })
end

local function render()
    local status = noctalia.state.get("status") or {}
    local busy = noctalia.state.get("busy") == true
    local running = status.service_active == true
    local items = type(status.items) == "table" and status.items or {}
    local recentDeals = type(status.recent_deals) == "table" and status.recent_deals or {}

    if not settingsSynced and status.desktop_notifications ~= nil then
        desktopNotif = status.desktop_notifications == true
        typedToken = tostring(status.telegram_bot_token or "")
        typedChatId = tostring(status.allowed_chat_id or "")
        settingsSynced = true
        settingsSeed += 1
    end

    local children = {
        buildHeader(status, running, busy),
        buildQuickAdd(busy),
    }
    if not running then
        table.insert(children, buildPausedNotice(busy))
    end
    table.insert(children, buildTabs(#recentDeals, #items))
    if activeTab == "watchlist" then
        table.insert(children, buildWatchlist(items, busy))
    elseif activeTab == "settings" then
        table.insert(children, buildSettings(busy))
    else
        table.insert(children, buildDeals(recentDeals))
    end
    table.insert(children, buildCoffeeCard())
    table.insert(children, buildFooter(status, busy))

    panel.render(ui.column({ gap = 12, flexGrow = 1 }, children))
end

function onCopyPix()
    sendCmd("copy-pix", "")
end

function onOpenPixQr()
    sendCmd("open-pix-qr", "")
end

function onToggleService()
    sendCmd("toggle-service", "")
end

function onShowDeals()
    activeTab = "deals"
    render()
end

function onShowWatchlist()
    activeTab = "watchlist"
    render()
end

function onToggleSettings()
    if activeTab == "settings" then
        activeTab = "deals"
    else
        activeTab = "settings"
    end
    render()
end

function onOpenHelp()
    sendCmd("open-help", "")
end

function onDesktopNotifChange(val)
    desktopNotif = val == true
end

function onTokenChange(val)
    typedToken = tostring(val or "")
end

function onChatIdChange(val)
    typedChatId = tostring(val or "")
end

function onTestNotify()
    sendCmd("test-notify", "")
end

function onSaveSettings()
    local flag = desktopNotif and "1" or "0"
    local payload = string.format(
        "%s|%s|%s",
        flag,
        noctalia.string.trim(typedToken),
        noctalia.string.trim(typedChatId)
    )
    sendCmd("save-settings", payload)
end

function onExclusiveChange(val)
    exclusive = val == true
    render()
end

function onQueryChange(val)
    typedQuery = tostring(val or "")
end

function onPriceChange(val)
    typedPrice = tostring(val or "")
end

function onQuerySubmit(val)
    typedQuery = tostring(val or typedQuery)
    submitProduct()
    render()
end

function onPriceSubmit(val)
    typedPrice = tostring(val or typedPrice)
    submitProduct()
    render()
end

function onAddProduct()
    submitProduct()
    render()
end

function onCheckNow()
    sendCmd("check-now", "")
end

function onClosePanel()
    panel.close()
end

function onOpen(_context)
    sendCmd("status", "")
    render()
end

noctalia.state.watch("status", function(_val)
    render()
end)

noctalia.state.watch("busy", function(_val)
    render()
end)
