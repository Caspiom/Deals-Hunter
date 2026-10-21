--!nonstrict

local function render(status)
    status = type(status) == "table" and status or {}
    local running = status.service_active == true
    local summary = tostring(status.summary or "Deal Hunter")
    local showQuery = noctalia.getConfig("show_query_in_bar") ~= false

    barWidget.setGlyph(running and "tag" or "tag-off")
    barWidget.setColor(running and "primary" or "outline")

    if showQuery then
        barWidget.setText(summary)
    else
        barWidget.setText("")
    end

    local stateLabel = running and "Monitorando" or "Pausado"
    barWidget.setTooltip(
        "Deal Hunter · " .. stateLabel .. ": " .. summary .. "\nClique: painel · Direito: ligar/desligar · Meio: buscar agora"
    )
end

noctalia.state.watch("status", render)

function update()
    render(noctalia.state.get("status"))
end

function onClick()
    noctalia.togglePanel("gappy/deal-hunter:panel")
end

function onRightClick()
    noctalia.state.set("cmd", { action = "toggle-service", arg = "", ts = os.clock() })
end

function onMiddleClick()
    noctalia.state.set("cmd", { action = "check-now", arg = "", ts = os.clock() })
end

render(noctalia.state.get("status"))
