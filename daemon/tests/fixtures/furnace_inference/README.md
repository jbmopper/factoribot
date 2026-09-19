# Furnace inference fixtures

These are synthetic contract graphs for task 19. They are hand-authored item
identity/conservation cases, not Factorio game observations and not evidence for
transport timing or achievable throughput.

- `iron_steel_chain`: an explicit iron-ore feed reaches one furnace, whose plate
  output reaches a second. The unique fixed point is iron-plate then steel-plate.
- `stone_brick`: stone is the only feed and the database coefficient is two stone
  per brick craft.
- `mixed_ores`: iron and copper ore reach the same furnace, so both plate recipes
  remain candidates.
- `conditional_source`: iron ore reaches the furnace only through a conditional
  arc; it may be a candidate but is not exact inference evidence.
- `unknown_bridge`: an unsupported possible bridge carries possible evidence but
  cannot establish a recipe.
- `no_source` and `disconnected_cycle`: neither is allowed to bootstrap material.
- `conflicting_override`: an explicit iron-plate override is retained while the
  confirmed feed contains only copper ore, and the conflict is reported.

All exact arcs are fixture assumptions. Their purpose is to test the inference
algorithm's evidence rules independently of the repository's still-unmet game
mechanics gate.

`pilot_policy.json` extends the existing illustrative pilot request with the four
base item-only smelting recipes. Its feed/export remain explicitly illustrative;
they are not declarations recovered from the owner. It exists only to show how
the 76 furnaces group when all real transport arcs remain relaxed/conditional.
