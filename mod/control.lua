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
    lbl.style.maximal_width = 380
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
  title.add{ type = "sprite-button", name = "factoribot_close",
             style = "frame_action_button", sprite = "utility/close",
             tooltip = "Close" }

  local body = frame.add{ type = "frame", name = "factoribot_body",
                          direction = "vertical", style = "inside_shallow_frame" }
  local out = body.add{ type = "scroll-pane", name = "factoribot_output",
                        direction = "vertical" }
  out.style.height = 320
  out.style.width = 400
  out.style.padding = 8

  local row = frame.add{ type = "flow", name = "factoribot_input_row",
                         direction = "horizontal" }
  row.style.top_padding = 8
  local tf = row.add{ type = "textfield", name = "factoribot_input" }
  tf.style.horizontally_stretchable = true
  tf.style.width = 330
  row.add{ type = "button", name = "factoribot_send", caption = "Send" }

  frame.force_auto_center()
  player.opened = frame
  tf.focus()
  render_log(player)
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

  local id = storage.next_id
  storage.next_id = id + 1
  storage.pending[id] = { player_index = player.index, log_index = log_index }

  local ok, err = pcall(function()
    helpers.send_udp(
      daemon_port(),
      helpers.table_to_json({ id = id, query = text, player = player.index }),
      player.index
    )
  end)
  if not ok then
    pdata.log[log_index] = { who = "err",
      text = "send failed (" .. tostring(err) .. "). Is the daemon running and "
             .. "Factorio launched with --enable-lua-udp?" }
    storage.pending[id] = nil
  end
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
  elseif el.name == "factoribot_close" then
    local player = game.get_player(e.player_index)
    local frame = player and player.gui.screen.factoribot_frame
    if frame then frame.destroy() end
  end
end)

script.on_event(defines.events.on_gui_confirmed, function(e)
  if e.element and e.element.valid and e.element.name == "factoribot_input" then
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
  if game.is_multiplayer() and #game.connected_players == 0 then return end
  helpers.recv_udp()
end)

script.on_event(defines.events.on_udp_packet_received, function(e)
  local decoded = helpers.json_to_table(e.payload)
  if not decoded or decoded.id == nil then return end
  local p = storage.pending[decoded.id]
  if not p then return end
  storage.pending[decoded.id] = nil

  local pdata = ensure_player(p.player_index)
  local text = decoded.text or ("error: " .. tostring(decoded.error))
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
