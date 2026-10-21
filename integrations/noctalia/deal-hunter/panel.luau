--!nonstrict

local typedQuery = ""
local typedPrice = ""
local inputSeed = 0

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

local function submitProduct(actionName)
    local payload = buildCombinedPayload()
    if payload ~= "" then
        sendCmd(actionName, payload)
        typedQuery = ""
        typedPrice = ""
        inputSeed += 1
    end
end

local function render()
    local status = noctalia.state.get("status") or {}
    local busy = noctalia.state.get("busy") == true
    local running = status.service_active == true
    local items = type(status.items) == "table" and status.items or {}

    local itemRows = {}
    for _idx, item in ipairs(items) do
        local isAct = item.active == true
        local itemId = tostring(item.id)
        local priceStr = string.format("<= R$ %.0f", tonumber(item.max_price) or 0)

        table.insert(itemRows, ui.row({
            gap = 8,
            align = "center",
            padding = 8,
            fill = isAct and "primary/0.2" or "surface_variant/0.4",
            radius = 8,
        }, {
            ui.toggle({
                checked = isAct,
                enabled = not busy,
                onChange = function(_val)
                    sendCmd("toggle-item", itemId)
                end,
            }),
            ui.column({ gap = 2, flexGrow = 1 }, {
                ui.label({
                    text = tostring(item.query),
                    fontWeight = "bold",
                    color = isAct and "primary" or "on_surface",
                }),
                ui.label({
                    text = priceStr,
                    fontSize = 11,
                    color = "on_surface_variant",
                }),
            }),
            ui.button({
                text = "Focar",
                variant = isAct and "primary" or "secondary",
                enabled = not busy,
                onClick = function()
                    sendCmd("select-only", itemId)
                end,
            }),
            ui.button({
                glyph = "trash",
                variant = "destructive",
                enabled = not busy,
                onClick = function()
                    sendCmd("del-item", itemId)
                end,
            }),
        }))
    end

    if #itemRows == 0 then
        table.insert(itemRows, ui.label({
            text = "Nenhum produto cadastrado.",
            color = "on_surface_variant",
        }))
    end

    panel.render(ui.column({ gap = 12, flexGrow = 1 }, {
        -- Cabeçalho + Botão de Fechar
        ui.row({ align = "center", justify = "space_between", gap = 8 }, {
            ui.row({ gap = 8, align = "center", flexGrow = 1 }, {
                ui.glyph({ name = running and "tag" or "tag-off", color = running and "primary" or "outline" }),
                ui.label({
                    text = "Deal Hunter Bot",
                    fontSize = 16,
                    fontWeight = "bold",
                    color = "on_surface",
                }),
            }),
            ui.button({
                glyph = "close",
                variant = "ghost",
                onClick = "onClosePanel",
            }),
        }),

        -- Controle Ligar / Desligar Serviço em Background
        ui.row({
            gap = 12,
            align = "center",
            justify = "space_between",
            padding = 10,
            fill = running and "primary/0.2" or "surface_variant/0.4",
            radius = 10,
        }, {
            ui.column({ gap = 2, flexGrow = 1 }, {
                ui.label({
                    text = running and "Bot Ligado (Monitorando)" or "Bot Desligado",
                    fontWeight = "bold",
                    color = running and "primary" or "on_surface",
                }),
                ui.label({
                    text = "Alvo atual: " .. tostring(status.summary or "Nenhum"),
                    fontSize = 12,
                    color = "on_surface_variant",
                }),
            }),
            ui.button({
                text = running and "Desligar" or "Ligar Bot",
                glyph = running and "player-stop" or "player-play",
                variant = running and "destructive" or "primary",
                enabled = not busy,
                onClick = "onToggleService",
            }),
        }),

        -- Campos separados para Nome do Produto e Valor Máximo
        ui.column({ gap = 8 }, {
            ui.row({ gap = 8, align = "center" }, {
                ui.column({ gap = 4, flexGrow = 2 }, {
                    ui.label({
                        text = "Nome do Produto:",
                        fontSize = 12,
                        fontWeight = "medium",
                        color = "on_surface_variant",
                    }),
                    ui.input({
                        key = "query-input-" .. tostring(inputSeed),
                        value = typedQuery,
                        placeholder = "Ex: fifine am8t",
                        onChange = "onQueryChange",
                        onSubmit = "onQuerySubmit",
                        enabled = not busy,
                    }),
                }),
                ui.column({ gap = 4, flexGrow = 1 }, {
                    ui.label({
                        text = "Valor Máx (R$):",
                        fontSize = 12,
                        fontWeight = "medium",
                        color = "on_surface_variant",
                    }),
                    ui.input({
                        key = "price-input-" .. tostring(inputSeed),
                        value = typedPrice,
                        placeholder = "Ex: 285",
                        onChange = "onPriceChange",
                        onSubmit = "onPriceSubmit",
                        enabled = not busy,
                    }),
                }),
            }),
            ui.row({ gap = 8, justify = "space_between" }, {
                ui.button({
                    text = "Pesquisar só este",
                    glyph = "target",
                    variant = "primary",
                    enabled = not busy,
                    onClick = "onSetExclusiveQuery",
                }),
                ui.button({
                    text = "Adicionar à lista",
                    glyph = "plus",
                    variant = "secondary",
                    enabled = not busy,
                    onClick = "onAddQuery",
                }),
            }),
        }),

        -- Lista de produtos na Watchlist
        ui.label({
            text = "Produtos na Watchlist:",
            fontSize = 12,
            fontWeight = "medium",
            color = "on_surface_variant",
        }),
        ui.scroll({ flexGrow = 1, gap = 8 }, itemRows),

        -- Rodapé: Forçar Varredura Agora
        ui.row({ gap = 8, align = "center", justify = "space_between" }, {
            ui.label({
                text = busy and "Processando..." or tostring(status.message or "Pronto"),
                fontSize = 11,
                color = "on_surface_variant",
                flexGrow = 1,
            }),
            ui.button({
                text = "Buscar Agora",
                glyph = "refresh",
                variant = "secondary",
                enabled = not busy,
                onClick = "onCheckNow",
            }),
        }),
    }))
end

function onToggleService()
    sendCmd("toggle-service", "")
end

function onQueryChange(val)
    typedQuery = tostring(val or "")
end

function onPriceChange(val)
    typedPrice = tostring(val or "")
end

function onQuerySubmit(val)
    typedQuery = tostring(val or typedQuery)
    submitProduct("set-query")
    render()
end

function onPriceSubmit(val)
    typedPrice = tostring(val or typedPrice)
    submitProduct("set-query")
    render()
end

function onSetExclusiveQuery()
    submitProduct("set-query")
    render()
end

function onAddQuery()
    submitProduct("add-item")
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
