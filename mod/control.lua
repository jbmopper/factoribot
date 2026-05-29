-- factoribot: in-game chat that talks to the local daemon over localhost UDP.
--
-- Requires launching Factorio with `--enable-lua-udp=<port>` and running the
-- daemon (`python -m factoribot.cli serve`). The mod sends questions to the
-- daemon's port (mod setting) and the daemon replies to the packet's source
-- (this game instance's UDP port), which we drain via recv_udp().

local DEFAULT_PORT = 25001

local function daemon_port()
  local s = settings.global["factoribot-daemon-port"]
  return (s and s.value) or DEFAULT_PORT
end

local function ensure_player(index)
  storage.players = storage.players or {}
  storage.players[index] = storage.players[index] or { log = {} }
  return storage.players[index]
end

-- Lifecycle -----------------------------------------------------------------

script.on_init(function()
  storage.pending = {}
  storage.next_id = 1
  storage.players = {}
  for _, p in pairs(game.players) do ensure_player(p.index) end
end)

script.on_configuration_changed(function()
  storage.pending = storage.pending or {}
  storage.next_id = storage.next_id or 1
  storage.players = storage.players or {}
  for _, p in pairs(game.players) do ensure_player(p.index) end
end)

script.on_event(defines.events.on_player_created, function(e)
  ensure_player(e.player_index)
end)

-- GUI -----------------------------------------------------------------------

local function render_log(player)
  local frame = player.gui.screen.factoribot_frame
  if not frame then return end
  local out = frame.factoribot_body.factoribot_output
  out.clear()
  for _, entry in ipairs(ensure_player(player.index).log) do
    local lbl = out.add{ type = "label", caption = entry.text }
    lbl.style.single_line = false
    lbl.style.maximal_width = 540
    if entry.who == "you" then
      lbl.style.font_color = { r = 0.6, g = 0.8, b = 1 }
    elseif entry.who == "err" then
      lbl.style.font_color = { r = 1, g = 0.5, b = 0.5 }
    end
  end
  pcall(function() out.scroll_to_bottom() end)
end

local function build_gui(player)
  if player.gui.screen.factoribot_frame then
    player.gui.screen.factoribot_frame.destroy()
    return
  end

  local frame = player.gui.screen.add{
    type = "frame", name = "factoribot_frame", direction = "vertical",
  }

  local title = frame.add{ type = "flow", direction = "horizontal" }
  title.drag_target = frame
  title.add{ type = "label", caption = "factoribot", style = "frame_title",
             ignored_by_interaction = true }
  local filler = title.add{ type = "empty-widget", style = "draggable_space_header",
                            ignored_by_interaction = true }
  filler.style.height = 24
  filler.style.horizontally_stretchable = true
  title.add{ type = "button", name = "factoribot_new", caption = "New",
             tooltip = "New conversation (clears the daemon's memory)" }
  title.add{ type = "sprite-button", name = "factoribot_close",
             style = "frame_action_button", sprite = "utility/close",
             tooltip = "Close" }

  local body = frame.add{ type = "frame", name = "factoribot_body",
                          direction = "vertical", style = "inside_shallow_frame" }
  local out = body.add{ type = "scroll-pane", name = "factoribot_output",
                        direction = "vertical" }
  out.style.height = 460
  out.style.width = 560
  out.style.padding = 8
  out.style.vertically_stretchable = true
  out.style.horizontally_stretchable = true

  local row = frame.add{ type = "flow", name = "factoribot_input_row",
                         direction = "horizontal" }
  row.style.top_padding = 8
  row.style.horizontally_stretchable = true
  row.style.vertical_align = "center"
  local tf = row.add{ type = "text-box", name = "factoribot_input" }
  tf.style.horizontally_stretchable = true
  tf.style.minimal_width = 470
  tf.style.height = 72
  row.add{ type = "button", name = "factoribot_send", caption = "Send" }

  local hint = frame.add{ type = "label",
                          caption = "Press Enter or click Send to ask." }
  hint.style.top_padding = 4
  hint.style.font_color = { r = 0.6, g = 0.6, b = 0.6 }

  frame.force_auto_center()
  player.opened = frame
  tf.focus()
  render_log(player)
end

local SEND_HINT = "Is the daemon running (factoribot serve) and Factorio "
  .. "launched with --enable-lua-udp?"

-- Send a query to the daemon; returns the request id, or nil + error string.
local function send_to_daemon(player, text)
  local id = storage.next_id
  storage.next_id = id + 1
  local ok, err = pcall(function()
    helpers.send_udp(
      daemon_port(),
      helpers.table_to_json({ id = id, query = text, player = player.index }),
      player.index
    )
  end)
  if not ok then return nil, tostring(err) end
  return id
end

local function submit(player)
  if not (player and player.valid) then return end
  local frame = player.gui.screen.factoribot_frame
  if not frame then return end
  local tf = frame.factoribot_input_row.factoribot_input
  local text = tf.text
  if not text or text == "" then return end
  tf.text = ""

  local pdata = ensure_player(player.index)
  table.insert(pdata.log, { who = "you", text = "> " .. text })
  table.insert(pdata.log, { who = "bot", text = "…thinking" })
  local log_index = #pdata.log

  local id, err = send_to_daemon(player, text)
  if id then
    storage.pending[id] = { player_index = player.index, log_index = log_index }
  else
    pdata.log[log_index] = { who = "err",
      text = "send failed (" .. err .. "). " .. SEND_HINT }
  end
  render_log(player)
end

-- Console: /factoribot <question>  (alias /fb)
local function ask_via_console(command)
  local player = game.get_player(command.player_index)
  if not player then return end
  local text = command.parameter and command.parameter:match("^%s*(.-)%s*$") or ""
  if text == "" then
    player.print("[factoribot] usage: /factoribot <question>  "
      .. "e.g. /factoribot purple science, assembly machine 2, no modules")
    return
  end
  local id, err = send_to_daemon(player, text)
  if id then
    storage.pending[id] = { player_index = player.index, console = true }
    player.print("[factoribot] thinking: " .. text)
  else
    player.print("[factoribot] send failed (" .. err .. "). " .. SEND_HINT)
  end
end

local function reset_conversation(player)
  if not (player and player.valid) then return end
  local pdata = ensure_player(player.index)
  pdata.log = { { who = "bot", text = "(new conversation)" } }

  local id = storage.next_id
  storage.next_id = id + 1
  -- Fire-and-forget: tell the daemon to forget this player's history. The reply
  -- has no matching pending entry, so the receiver simply ignores it.
  pcall(function()
    helpers.send_udp(
      daemon_port(),
      helpers.table_to_json({ id = id, reset = true, player = player.index }),
      player.index
    )
  end)
  render_log(player)
end

-- Input events --------------------------------------------------------------

script.on_event("factoribot-toggle", function(e)
  local player = game.get_player(e.player_index)
  if player then build_gui(player) end
end)

script.on_event(defines.events.on_gui_click, function(e)
  local el = e.element
  if not (el and el.valid) then return end
  if el.name == "factoribot_send" then
    submit(game.get_player(e.player_index))
  elseif el.name == "factoribot_new" then
    reset_conversation(game.get_player(e.player_index))
  elseif el.name == "factoribot_close" then
    local player = game.get_player(e.player_index)
    local frame = player and player.gui.screen.factoribot_frame
    if frame then frame.destroy() end
  end
end)

-- A text-box doesn't fire on_gui_confirmed; pressing Enter just appends a newline.
-- Treat a trailing newline as "send" (and strip it back out). Multi-line text
-- pasted without a trailing newline stays put until Enter or the Send button.
script.on_event(defines.events.on_gui_text_changed, function(e)
  local el = e.element
  if not (el and el.valid and el.name == "factoribot_input") then return end
  local text = el.text
  if text ~= "" and text:sub(-1) == "\n" then
    el.text = text:sub(1, -2)
    submit(game.get_player(e.player_index))
  end
end)

script.on_event(defines.events.on_gui_closed, function(e)
  if e.element and e.element.valid and e.element.name == "factoribot_frame" then
    e.element.destroy()
  end
end)

-- UDP bridge ----------------------------------------------------------------

script.on_nth_tick(20, function()
  -- We send with for_player = player.index, so the reply lands on that player's
  -- socket; recv_udp(for_player) only drains the socket you name. Poll the server
  -- socket (0, for the host) and every connected player's socket. Wrapped in
  -- pcall so a missing --enable-lua-udp doesn't spam errors every tick.
  pcall(function()
    helpers.recv_udp(0)
    for _, p in pairs(game.connected_players) do
      helpers.recv_udp(p.index)
    end
  end)
end)

script.on_event(defines.events.on_udp_packet_received, function(e)
  local decoded = helpers.json_to_table(e.payload)
  if not decoded or decoded.id == nil then return end
  local p = storage.pending[decoded.id]
  if not p then return end
  storage.pending[decoded.id] = nil

  local text = decoded.text or ("error: " .. tostring(decoded.error))

  if p.console then
    local player = game.get_player(p.player_index)
    if player then player.print("[factoribot] " .. text) end
    return
  end

  local pdata = ensure_player(p.player_index)
  if pdata.log[p.log_index] then
    pdata.log[p.log_index] = { who = "bot", text = text }
  else
    table.insert(pdata.log, { who = "bot", text = text })
  end

  local player = game.get_player(p.player_index)
  if player then
    if player.gui.screen.factoribot_frame then
      render_log(player)
    else
      player.print("[factoribot] " .. text)
    end
  end
end)

-- Console commands -----------------------------------------------------------

commands.add_command(
  "factoribot",
  "Ask factoribot a factory-design question, e.g. /factoribot purple science, AM2",
  ask_via_console
)
pcall(function()
  commands.add_command("fb", "Alias for /factoribot.", ask_via_console)
end)
