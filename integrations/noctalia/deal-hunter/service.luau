--!nonstrict

local PYTHON_BIN = "__INSTALL_DIR__/.venv/bin/python"
local CTL_SCRIPT = "__INSTALL_DIR__/ctl.py"

local busy = false

local function runCtl(cmd, arg, silent)
    if busy and cmd == "status" then
        return
    end
    busy = true
    noctalia.state.set("busy", true)

    local argv = { PYTHON_BIN, CTL_SCRIPT, cmd }
    if type(arg) == "string" and arg ~= "" then
        table.insert(argv, arg)
    end

    local accepted = noctalia.runAsync(argv, function(result)
        busy = false
        noctalia.state.set("busy", false)
        local data = noctalia.json.decode(result.stdout or "")
        if type(data) ~= "table" then
            data = {
                service_active = false,
                summary = "Erro",
                message = "Falha ao executar ctl.py",
                items = {},
            }
        end
        noctalia.state.set("status", data)
        if not silent and type(data.message) == "string" and data.message ~= "" then
            noctalia.notify(noctalia.tr("title"), data.message)
        end
    end, 45000)

    if not accepted then
        busy = false
        noctalia.state.set("busy", false)
    end
end

noctalia.state.watch("cmd", function(payload)
    if type(payload) ~= "table" then
        return
    end
    local action = tostring(payload.action or "status")
    local arg = tostring(payload.arg or "")
    runCtl(action, arg, action == "status")
end)

noctalia.setUpdateInterval(5000)

function update()
    runCtl("status", "", true)
end

function onIpc(event, payload)
    runCtl(tostring(event or "status"), tostring(payload or ""), false)
end

runCtl("status", "", true)
