/* Routing audit viewer.
 *
 * Displays contract data only. Every analysis number shown here was formatted
 * in Python and is copied verbatim; this script derives no finding, bound or
 * rate. All imported text is inserted with textContent, never as markup.
 * The map is one canvas: no DOM element is created per arc, lane or entity.
 */
(function () {
  "use strict";

  var D = JSON.parse(document.getElementById("factoribot-view-data").textContent);
  var G = D.graph || {};
  var R = D.result || null;
  var REQ = R && R.request ? R.request : null;

  /* ---------------------------------------------------------------- utils */

  function E(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined && text !== null) { node.textContent = String(text); }
    return node;
  }
  function add(parent, node) { parent.appendChild(node); return node; }
  function dash(value) { return (value === undefined || value === null || value === "") ? "—" : String(value); }
  function kv(parent, key, value) {
    var wrap = E("div", "kv");
    add(wrap, E("span", "k", key));
    add(wrap, E("span", "v", dash(value)));
    return add(parent, wrap);
  }
  function list(parent, values, empty) {
    if (!values || !values.length) { add(parent, E("p", "note", empty || "none")); return; }
    var ul = E("ul", "plain");
    values.forEach(function (value) { add(ul, E("li", null, String(value))); });
    add(parent, ul);
  }
  function extras(parent, extra, label) {
    var keys = extra ? Object.keys(extra) : [];
    if (!keys.length) { return; }
    add(parent, E("p", "small", (label || "Additional fields in this record") + " (shown generically):"));
    keys.sort().forEach(function (key) { kv(parent, key, extra[key]); });
  }
  function canon(value) {
    if (value === null || typeof value !== "object") { return JSON.stringify(value === undefined ? null : value); }
    if (Array.isArray(value)) { return "[" + value.map(canon).join(",") + "]"; }
    return "{" + Object.keys(value).sort().map(function (key) {
      return JSON.stringify(key) + ":" + canon(value[key]);
    }).join(",") + "}";
  }
  function entKey(id) {
    if (!id || typeof id !== "object") { return "bp/?/e/?"; }
    var path = Array.isArray(id.book_path) ? id.book_path : [];
    return "bp/" + (path.join("/") || "root") + "/e/" + id.entity_number;
  }
  function epKey(id) {
    if (!id || typeof id !== "object") { return "?/?"; }
    return entKey(id.entity) + "/" + id.kind + "/" + id.name;
  }
  var TOKEN = /^[a-z][a-z0-9_-]*$/;

  /* --------------------------------------------------------------- indexes */

  var entityByKey = {}, endpointByKey = {}, arcById = {}, evidenceById = {};
  (G.entities || []).forEach(function (e) { entityByKey[e.key] = e; });
  [].concat(G.ports || [], G.lanes || [], G.inventories || []).forEach(function (p) { endpointByKey[p.key] = p; });
  (G.arcs || []).forEach(function (a) { arcById[a.id] = a; });
  (G.evidence || []).forEach(function (e) { evidenceById[e.id] = e; });
  var findings = (R && R.findings) || [];
  var findingById = {};
  findings.forEach(function (f) { findingById[f.id] = f; });

  /* ------------------------------------------------------- editable state */

  function copyAssignments(source) {
    source = source || {};
    return {
      schema_version: source.schema_version !== undefined ? source.schema_version : G.schema_version,
      blueprint_hash: source.blueprint_hash !== undefined ? source.blueprint_hash : G.blueprint_hash,
      graph_hash: source.graph_hash !== undefined ? source.graph_hash : G.graph_hash,
      feeds: (source.feeds || []).map(function (f) {
        return { id: f.id, budget_id: f.budget_id, endpoint: f.endpoint, capacity: f.capacity };
      }),
      furnaces: (source.furnaces || []).map(function (f) { return { entity: f.entity, recipe: f.recipe }; }),
      controls: (source.controls || []).map(function (c) { return { condition: c.condition, enabled: c.enabled }; })
    };
  }
  var A = copyAssignments(D.assignments);
  var ANALYSED = D.analyzed_assignments ? canon(assignmentDoc(copyAssignments(D.analyzed_assignments))) : null;
  var LOADED = null;

  function assignmentDoc(state) {
    var s = state || A;
    return {
      schema_version: s.schema_version,
      blueprint_hash: s.blueprint_hash,
      graph_hash: s.graph_hash,
      feeds: s.feeds.map(function (f) {
        return { id: f.id, budget_id: f.budget_id, endpoint: f.endpoint, capacity: f.capacity };
      }),
      furnaces: s.furnaces.map(function (f) { return { entity: f.entity, recipe: f.recipe }; }),
      controls: s.controls.map(function (c) { return { condition: c.condition, enabled: c.enabled }; })
    };
  }
  LOADED = canon(assignmentDoc());

  var proposed = {
    budgets: (REQ ? REQ.budgets : []).map(function (b) {
      return { id: b.id, material: b.material, capacity: b.capacity };
    }),
    exports: (REQ ? REQ.exports : []).map(function (x) { return x.record; }).filter(Boolean),
    surplus: (REQ ? REQ.surplus : []).map(function (x) { return x.record; }).filter(Boolean),
    objective: REQ ? { kind: REQ.objective.kind, export_id: REQ.objective.export_id } : { kind: "feasible", export_id: null }
  };

  var state = {
    tab: "findings",
    finding: null,
    selEntities: {},
    selEndpoints: {},
    importMessage: null,
    importText: "",
    importOk: false,
    entityFilter: ""
  };
  var HL = { entities: {}, endpoints: {}, arcs: {} };

  /* ------------------------------------------------------------ staleness */

  function staleReport() {
    var hard = [], soft = [];
    if (A.blueprint_hash !== G.blueprint_hash) {
      hard.push("Stale blueprint hash: assignments carry " + dash(A.blueprint_hash) + ", this graph is " + dash(G.blueprint_hash) + ".");
    }
    if (A.graph_hash !== G.graph_hash) {
      hard.push("Stale graph hash: assignments carry " + dash(A.graph_hash) + ", this graph is " + dash(G.graph_hash) + ".");
    }
    if (R && ANALYSED !== null && canon(assignmentDoc()) !== ANALYSED) {
      soft.push("The displayed analysis was produced for a different assignment set. It no longer describes these edits; re-run the host analysis.");
    }
    if (R && ANALYSED === null) {
      soft.push("The displayed result carries no interpreted assignments, so these edits cannot be matched against it.");
    }
    if (R && R.graph_match === false) {
      hard.push("The displayed result was produced for a different graph or blueprint than the one loaded here.");
    }
    return { hard: hard, soft: soft, edited: canon(assignmentDoc()) !== LOADED };
  }

  /* --------------------------------------------------------------- layout */

  var app = document.getElementById("app");
  var header = add(app, E("header", "top"));
  var main = add(app, E("main"));
  var side = add(main, E("section")); side.id = "side";
  var tabsBar = add(side, E("div")); tabsBar.id = "tabs";
  var panel = add(side, E("div")); panel.id = "panel";
  var stage = add(main, E("section")); stage.id = "stage";
  var canvas = add(stage, E("canvas")); canvas.id = "map";
  var tools = add(stage, E("div")); tools.id = "tools";
  var legend = add(stage, E("div")); legend.id = "legend";
  var statusBar = add(stage, E("div")); statusBar.id = "status";
  var banners = null;

  function renderHeader() {
    header.textContent = "";
    add(header, E("h1", null, D.title));
    var chips = add(header, E("div", "chips"));
    add(chips, E("span", "chip", "provenance: " + dash(G.provenance)));
    add(chips, E("span", "chip", "profile: " + dash(G.mechanics_profile)));
    add(chips, E("span", "chip", "graph schema: " + dash(G.schema_version)));
    if (R) {
      add(chips, E("span", "chip", "status: " + dash(R.status)));
      add(chips, E("span", "chip", "analyzer: " + dash(R.analyzer_version)));
    } else {
      add(chips, E("span", "chip", "no analysis result loaded"));
    }
    add(chips, E("span", "chip mono", "graph " + dash(G.graph_hash_short)));
    add(chips, E("span", "chip mono", "blueprint " + dash(G.blueprint_hash_short)));
    banners = add(header, E("div"));
    renderBanners();
  }

  function renderBanners() {
    if (!banners) { return; }
    banners.textContent = "";
    var report = staleReport();
    report.hard.forEach(function (text) { add(banners, E("div", "banner err", "STALE: " + text)); });
    report.soft.forEach(function (text) { add(banners, E("div", "banner", "STALE: " + text)); });
    if (!report.hard.length && !report.soft.length && report.edited) {
      add(banners, E("div", "banner ok", "Assignments edited in this page; they still match the analysed request."));
    }
    if (R) {
      add(banners, E("div", "banner ok", R.status_text));
    }
  }

  var TABS = [
    ["findings", "Findings"],
    ["model", "Model"],
    ["assign", "Assignments"],
    ["io", "Export / import"],
    ["selection", "Selection"]
  ];
  TABS.forEach(function (pair) {
    var button = add(tabsBar, E("button", null, pair[1]));
    button.setAttribute("role", "tab");
    button.dataset.tab = pair[0];
    button.addEventListener("click", function () { state.tab = pair[0]; renderPanel(); });
  });

  function renderPanel() {
    Array.prototype.forEach.call(tabsBar.children, function (b) {
      b.setAttribute("aria-selected", b.dataset.tab === state.tab ? "true" : "false");
    });
    panel.textContent = "";
    panel.scrollTop = 0;
    if (state.tab === "findings") { renderFindings(panel); }
    else if (state.tab === "model") { renderModel(panel); }
    else if (state.tab === "assign") { renderAssign(panel); }
    else if (state.tab === "io") { renderIo(panel); }
    else { renderSelection(panel); }
  }

  /* ------------------------------------------------------- findings panel */

  function scopeLine(parent, label, keys) {
    if (!keys || !keys.length) { return; }
    var wrap = add(parent, E("div", "small"));
    add(wrap, E("span", null, label + ": "));
    keys.forEach(function (key, index) {
      if (index) { add(wrap, E("span", null, ", ")); }
      add(wrap, E("span", "mono", key));
    });
  }

  function renderFindings(root) {
    add(root, E("h2", null, "Analysis"));
    if (!R) {
      add(root, E("p", "note", "No analysis result was supplied to the renderer. The map below shows the graph only."));
      return;
    }
    add(root, E("p", "note", R.status_text));
    kv(root, "result hash", R.result_hash);
    kv(root, "request hash", R.request_hash);
    kv(root, "detail scope", R.detail_kind);
    kv(root, "witness", R.witness_present ? ("present (" + dash(R.witness_validation) + ")") : "none");
    extras(root, R.extra, "Additional result fields");

    add(root, E("h2", null, "Findings (" + findings.length + ")"));
    add(root, E("p", "note", "Severity and evidence kind are written out in words and marked by border style, so they do not depend on colour."));
    if (!findings.length) { add(root, E("p", "note", "none")); }
    findings.forEach(function (finding) {
      var card = add(root, E("div", "card sev-" + finding.severity + (state.finding === finding.id ? " sel" : "")));
      card.tabIndex = 0;
      var head = add(card, E("div"));
      var mark = finding.severity === "error" ? "✖ ERROR" : (finding.severity === "warning" ? "▲ WARNING" : "● INFO");
      add(head, E("span", "badge " + finding.severity, mark));
      add(head, E("span", "badge kind", "evidence: " + finding.evidence_kind));
      add(head, E("span", "mono", finding.code));
      add(card, E("p", "msg", finding.message));
      add(card, E("p", "small", finding.evidence_kind_text));
      add(card, E("p", "small", finding.runtime_note));
      if (finding.material_text) { kv(card, "material", finding.material_text); }
      if (finding.required_rate_text) { kv(card, "required rate", finding.required_rate_text); }
      if (finding.capacity_upper_bound_text) {
        kv(card, "upper bound under stated relaxations", finding.capacity_upper_bound_text);
      }
      scopeLine(card, "entities", finding.entity_keys);
      scopeLine(card, "endpoints", finding.endpoint_keys);
      scopeLine(card, "evidence", finding.evidence_ids);
      scopeLine(card, "highlights arcs", finding.highlight.arcs);
      list(card, finding.assumptions, "no extra assumptions recorded");
      extras(card, finding.extra, "Additional finding fields");
      kv(card, "finding id", finding.id);
      card.addEventListener("click", function () { selectFinding(finding.id); });
      card.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectFinding(finding.id); }
      });
    });

    var bounds = R.bounds || [];
    add(root, E("h2", null, "Upper bounds (" + bounds.length + ")"));
    add(root, E("p", "note", "Each value is an upper bound under the stated relaxations. It is never an achievable or measured rate."));
    if (!bounds.length) { add(root, E("p", "note", "No bound is advertised for this result.")); }
    bounds.forEach(function (bound) {
      var card = add(root, E("div", "card plain sev-info"));
      add(card, E("div", null, "stage " + bound.stage + " — " + bound.direction + " bound"));
      add(card, E("p", "small", bound.stage_text));
      kv(card, "value", bound.value_text);
      kv(card, "objective export", bound.objective_export_id);
      kv(card, "solver state", bound.solver_state);
      add(card, E("p", "small", "relaxations:"));
      list(card, bound.relaxations, "none declared");
      add(card, E("p", "small", "assumptions:"));
      list(card, bound.assumptions, "none declared");
      add(card, E("p", "small", "certificate (producer attestation, not a proof checked here):"));
      add(card, E("p", "msg", bound.certificate));
      kv(card, "comparison hash", bound.comparison_hash);
      kv(card, "constraint hash", bound.constraint_hash);
      extras(card, bound.extra, "Additional bound fields");
    });

    add(root, E("h2", null, "Result assumptions"));
    list(root, R.assumptions, "none recorded");
    add(root, E("h2", null, "Result limitations"));
    list(root, R.limitations, "none recorded");
    add(root, E("h2", null, "Page notes"));
    list(root, D.notes);
  }

  /* ---------------------------------------------------------- model panel */

  function renderModel(root) {
    add(root, E("h2", null, "Graph"));
    var counts = G.counts || {};
    Object.keys(counts).forEach(function (key) { kv(root, key.replace(/_/g, " "), counts[key]); });
    kv(root, "selected book paths", (G.selected_paths || []).join(" "));
    kv(root, "blueprint hash", G.blueprint_hash);
    kv(root, "prototype hash", G.prototype_hash);
    kv(root, "graph hash", G.graph_hash);
    extras(root, G.extra, "Additional graph fields");

    var unsupported = (G.entities || []).filter(function (e) { return e.support !== "supported"; });
    add(root, E("h2", null, "Unsupported / conditional entities (" + unsupported.length + ")"));
    add(root, E("p", "note", "These stay visible on the map. They cannot become supported activities, and they block bounds unless the request declares them out of scope."));
    unsupported.forEach(function (entity) { add(root, entityRow(entity)); });
    if (!unsupported.length) { add(root, E("p", "note", "none")); }

    var gaps = G.topology_gaps || [];
    add(root, E("h2", null, "Unsupported possible topology (" + gaps.length + ")"));
    gaps.forEach(function (gap) {
      var card = add(root, E("div", "card sev-warning"));
      add(card, E("span", "badge warning", "▲ GAP"));
      add(card, E("span", "mono", gap.id));
      add(card, E("p", "msg", gap.reason));
      kv(card, "may connect", gap.may_connect ? "yes" : "no");
      scopeLine(card, "entities", gap.entity_keys);
      scopeLine(card, "possible endpoints", gap.endpoint_keys);
      extras(card, gap.extra, "Additional gap fields");
      card.addEventListener("click", function () {
        HL = { entities: keySet(gap.entity_keys), endpoints: keySet(gap.endpoint_keys), arcs: {} };
        state.finding = null;
        focusKeys(gap.entity_keys, gap.endpoint_keys, []);
        renderPanel(); request();
      });
    });
    if (!gaps.length) { add(root, E("p", "note", "none")); }

    add(root, E("h2", null, "Capacity groups (" + (G.capacity_groups || []).length + ")"));
    (G.capacity_groups || []).forEach(function (group) {
      var row = add(root, E("div", "row"));
      add(row, E("span", "mono", group.id));
      add(row, E("span", "grow small", group.kind + " · " + group.capacity_text));
    });

    add(root, E("h2", null, "Activities (" + (G.activities || []).length + ")"));
    (G.activities || []).forEach(function (activity) {
      var card = add(root, E("div", "card plain"));
      add(card, E("div", "mono", activity.id + " · " + activity.recipe));
      kv(card, "entity", activity.entity_key);
      kv(card, "craft capacity", activity.craft_capacity_text);
      activity.inputs.forEach(function (part) {
        kv(card, "in " + part.material_text, part.amount_text + " per craft @ " + part.endpoint_key);
      });
      activity.outputs.forEach(function (part) {
        kv(card, "out " + part.material_text, part.amount_text + " per craft @ " + part.endpoint_key);
      });
      activity.resources.forEach(function (use) { kv(card, "machine time group", use.group_id + " × " + use.coefficient_text); });
      extras(card, activity.extra, "Additional activity fields");
    });
    if (!(G.activities || []).length) { add(root, E("p", "note", "none")); }

    add(root, E("h2", null, "Evidence (" + (G.evidence || []).length + ")"));
    (G.evidence || []).forEach(function (evidence) {
      var card = add(root, E("div", "card plain"));
      add(card, E("span", "badge kind", evidence.kind));
      add(card, E("span", "mono", evidence.id));
      add(card, E("p", "msg", evidence.description));
      evidence.sources.forEach(function (source) { kv(card, source.source, source.uri + " " + source.pointer); });
      scopeLine(card, "arc path", evidence.arc_path);
      extras(card, evidence.extra, "Additional evidence fields");
    });

    if (REQ) { renderRequest(root); }

    add(root, E("h2", null, "Entities (" + (G.entities || []).length + ")"));
    var search = add(root, E("input"));
    search.type = "text";
    search.placeholder = "filter by key or prototype";
    search.value = state.entityFilter;
    var results = add(root, E("div"));
    function fill() {
      results.textContent = "";
      var needle = state.entityFilter.toLowerCase();
      var matched = (G.entities || []).filter(function (entity) {
        return !needle || entity.key.toLowerCase().indexOf(needle) >= 0 || entity.prototype.toLowerCase().indexOf(needle) >= 0;
      });
      add(results, E("p", "small", "showing " + Math.min(matched.length, 200) + " of " + matched.length + " matching entities (the map draws all of them)"));
      matched.slice(0, 200).forEach(function (entity) { add(results, entityRow(entity)); });
    }
    search.addEventListener("input", function () { state.entityFilter = search.value; fill(); });
    fill();
  }

  function renderRequest(root) {
    add(root, E("h2", null, "Interpreted request"));
    kv(root, "objective", REQ.objective_text);
    add(root, E("p", "small", "Global material budgets — feeds sharing an ID draw on one ceiling:"));
    (REQ.budgets || []).forEach(function (budget) {
      var row = add(root, E("div", "row"));
      add(row, E("span", "mono", budget.id));
      add(row, E("span", "grow small", budget.material_text + " · " + budget.capacity_text));
    });
    add(root, E("p", "small", "Exports (net rates, external removal required):"));
    (REQ.exports || []).forEach(function (item) {
      var card = add(root, E("div", "card plain"));
      add(card, E("div", "mono", item.id));
      kv(card, "material", item.material_text);
      kv(card, "requirement", item.requirement + " " + item.rate_text);
      kv(card, "endpoint", item.endpoint_key);
      kv(card, "sink", item.sink_service);
      kv(card, "sink ceiling", item.sink_capacity_text);
    });
    if ((REQ.surplus || []).length) {
      add(root, E("p", "small", "Surplus outlets:"));
      (REQ.surplus || []).forEach(function (item) {
        var card = add(root, E("div", "card plain"));
        add(card, E("div", "mono", item.id));
        kv(card, "material", item.material_text);
        kv(card, "endpoint", item.endpoint_key);
        kv(card, "sink", item.sink_service);
      });
    }
    add(root, E("h2", null, "Request assumptions"));
    (REQ.assumptions.rows || []).forEach(function (pair) { kv(root, pair[0], pair[1]); });
    var irrelevant = REQ.assumptions.irrelevant || [];
    if (irrelevant.length) {
      add(root, E("p", "small", "Declared irrelevant subsystems (scoped out of the item model by the request):"));
      irrelevant.forEach(function (declaration) {
        var card = add(root, E("div", "card sev-info"));
        add(card, E("span", "badge info", "● DECLARED"));
        add(card, E("span", "mono", declaration.id));
        kv(card, "subsystem", declaration.subsystem);
        kv(card, "basis", declaration.basis);
        add(card, E("p", "msg", declaration.justification));
        scopeLine(card, "entities", declaration.entity_keys);
      });
    }
    extras(root, REQ.assumptions.extra, "Additional assumption fields");
    kv(root, "protected areas", REQ.protected.areas);
    scopeLine(root, "protected entities", REQ.protected.entities);
    scopeLine(root, "protected endpoints", REQ.protected.endpoints);
    list(root, REQ.protected.flags, "no protection flags recorded");
    extras(root, REQ.extra, "Additional request fields");
  }

  function entityRow(entity) {
    var row = E("div", "row" + (state.selEntities[entity.key] ? " sel" : ""));
    add(row, E("span", "mono", entity.key));
    var detail = entity.prototype + " · " + entity.support;
    if (entity.subsystem) { detail += " · " + entity.subsystem; }
    if (entity.mod) { detail += " · mod " + entity.mod; }
    add(row, E("span", "grow small", detail));
    row.style.cursor = "pointer";
    row.addEventListener("click", function () { selectEntity(entity.key, false); });
    return row;
  }

  /* ---------------------------------------------------- assignments panel */

  function budgetOptions() {
    return proposed.budgets.map(function (b) { return b.id; });
  }

  function renderAssign(root) {
    var report = staleReport();
    if (report.hard.length || report.soft.length) {
      report.hard.concat(report.soft).forEach(function (text) { add(root, E("div", "banner err", "STALE: " + text)); });
    }
    add(root, E("h2", null, "Global budgets"));
    add(root, E("p", "note", "Two feeds naming one budget ID share a single global ceiling; they do not each receive it. Click a budget to select every port that draws on it."));
    proposed.budgets.forEach(function (budget) {
      var users = A.feeds.filter(function (f) { return f.budget_id === budget.id; });
      var row = add(root, E("div", "row"));
      add(row, E("span", "mono", budget.id));
      add(row, E("span", "grow small", materialText(budget.material) + " · ceiling " + capacityText(budget.capacity)
        + " · " + users.length + " feed(s) share it"));
      row.style.cursor = "pointer";
      row.addEventListener("click", function () {
        state.selEndpoints = {};
        users.forEach(function (feed) { state.selEndpoints[epKey(feed.endpoint)] = true; });
        state.selEntities = {};
        state.tab = "selection";
        focusKeys([], Object.keys(state.selEndpoints), []);
        renderPanel(); request();
      });
    });
    if (!proposed.budgets.length) { add(root, E("p", "note", "none declared yet")); }
    add(root, budgetForm());

    add(root, E("h2", null, "Feeds (" + A.feeds.length + ")"));
    A.feeds.forEach(function (feed, index) {
      var row = add(root, E("div", "row" + (state.selEndpoints[epKey(feed.endpoint)] ? " sel" : "")));
      add(row, E("span", "mono", feed.id));
      add(row, E("span", "grow small", "budget " + feed.budget_id + " · " + capacityText(feed.capacity) + " · " + epKey(feed.endpoint)));
      var pick = add(row, E("button", "mini", "select port"));
      pick.addEventListener("click", function (event) {
        event.stopPropagation();
        state.selEndpoints[epKey(feed.endpoint)] = true;
        renderPanel(); request();
      });
      var drop = add(row, E("button", "mini", "remove"));
      drop.addEventListener("click", function (event) {
        event.stopPropagation();
        A.feeds.splice(index, 1);
        changed();
      });
    });
    if (!A.feeds.length) { add(root, E("p", "note", "none")); }
    add(root, feedForm());

    add(root, E("h2", null, "Exports and surplus (request draft only)"));
    add(root, E("p", "note", "Outlets belong to the routing request, not to the assignment set. They are written to the draft export document for the host."));
    proposed.exports.forEach(function (item, index) {
      var row = add(root, E("div", "row"));
      add(row, E("span", "mono", item.id));
      add(row, E("span", "grow small", "export " + materialText(item.material) + " · " + item.requirement + " " + item.rate + " · " + epKey(item.endpoint)));
      var drop = add(row, E("button", "mini", "remove"));
      drop.addEventListener("click", function () { proposed.exports.splice(index, 1); changed(); });
    });
    proposed.surplus.forEach(function (item, index) {
      var row = add(root, E("div", "row"));
      add(row, E("span", "mono", item.id));
      add(row, E("span", "grow small", "surplus " + materialText(item.material) + " · " + epKey(item.endpoint)));
      var drop = add(row, E("button", "mini", "remove"));
      drop.addEventListener("click", function () { proposed.surplus.splice(index, 1); changed(); });
    });
    add(root, outletForm());

    add(root, E("h2", null, "Furnace recipe assignment"));
    add(root, E("p", "note", "Only a recipe recorded as a candidate of that entity may be assigned. Several candidates with no override leave the model unresolved, which forces a partial result with no bounds."));
    var furnaceEntities = (G.entities || []).filter(function (e) { return e.furnace_candidates && e.furnace_candidates.length; });
    furnaceEntities.forEach(function (entity) {
      var current = null;
      A.furnaces.forEach(function (f) { if (entKey(f.entity) === entity.key) { current = f; } });
      var wrap = add(root, E("div", "card plain"));
      add(wrap, E("div", "mono", entity.key + " · " + entity.prototype));
      var label = add(wrap, E("label", "field"));
      add(label, E("span", null, "recipe (" + entity.furnace_candidates.length + " candidate(s))"));
      var select = add(label, E("select"));
      var none = add(select, E("option", null, "(unresolved — no override)"));
      none.value = "";
      entity.furnace_candidates.forEach(function (recipe) {
        var option = add(select, E("option", null, recipe));
        option.value = recipe;
      });
      select.value = current ? current.recipe : "";
      if (!current && entity.furnace_candidates.length > 1) {
        add(wrap, E("p", "small err-text", "Unresolved: this entity has several candidates and no assignment."));
      }
      select.addEventListener("change", function () {
        A.furnaces = A.furnaces.filter(function (f) { return entKey(f.entity) !== entity.key; });
        if (select.value) { A.furnaces.push({ entity: entity.id, recipe: select.value }); }
        changed();
      });
    });
    if (!furnaceEntities.length) { add(root, E("p", "note", "no entity in this graph records furnace candidates")); }

    add(root, E("h2", null, "Circuit control assignments"));
    var conditions = G.conditions || [];
    if (!conditions.length) { add(root, E("p", "note", "no arc in this graph names a condition")); }
    conditions.forEach(function (condition) {
      var current = null;
      A.controls.forEach(function (c) { if (c.condition === condition) { current = c; } });
      var label = add(root, E("label", "field"));
      add(label, E("span", null, condition));
      var select = add(label, E("select"));
      [["", "(unset — relax_open policy)"], ["true", "enabled"], ["false", "disabled"]].forEach(function (pair) {
        var option = add(select, E("option", null, pair[1]));
        option.value = pair[0];
      });
      select.value = current ? String(current.enabled) : "";
      select.addEventListener("change", function () {
        A.controls = A.controls.filter(function (c) { return c.condition !== condition; });
        if (select.value) { A.controls.push({ condition: condition, enabled: select.value === "true" }); }
        changed();
      });
    });
  }

  function field(parent, labelText, value, placeholder) {
    var label = add(parent, E("label", "field"));
    add(label, E("span", null, labelText));
    var input = add(label, E("input"));
    input.type = "text";
    if (value !== undefined && value !== null) { input.value = value; }
    if (placeholder) { input.placeholder = placeholder; }
    return input;
  }
  function choice(parent, labelText, options, value) {
    var label = add(parent, E("label", "field"));
    add(label, E("span", null, labelText));
    var select = add(label, E("select"));
    options.forEach(function (pair) {
      var option = add(select, E("option", null, pair[1]));
      option.value = pair[0];
    });
    if (value !== undefined) { select.value = value; }
    return select;
  }
  function materialText(material) {
    if (!material) { return "—"; }
    return material.name + (material.kind !== "item" ? " (" + material.kind + ")" : "")
      + (material.quality && material.quality !== "normal" ? " [" + material.quality + "]" : "");
  }
  function capacityText(capacity) {
    if (!capacity) { return "—"; }
    if (capacity.kind === "finite") { return String(capacity.value); }
    return capacity.kind;
  }
  function numberOrNull(text) {
    if (!/^-?(0|[1-9][0-9]*)(\.[0-9]+)?$/.test(String(text).trim())) { return null; }
    var value = Number(text);
    return isFinite(value) ? value : null;
  }

  function budgetForm() {
    var form = E("div", "card plain");
    add(form, E("div", null, "Declare a global budget"));
    var id = field(form, "budget id (token)", "", "iron");
    var name = field(form, "material name", "", "iron-plate");
    var kind = choice(form, "material kind", [["item", "item"], ["fluid", "fluid"]], "item");
    var capKind = choice(form, "ceiling", [["finite", "finite"], ["unlimited", "unlimited"]], "finite");
    var capValue = field(form, "ceiling value (items/s)", "", "10");
    var message = add(form, E("p", "small"));
    var button = add(form, E("button", "act", "Add budget"));
    button.addEventListener("click", function () {
      var errors = [];
      if (!TOKEN.test(id.value)) { errors.push("budget id must match [a-z][a-z0-9_-]*"); }
      if (!TOKEN.test(name.value)) { errors.push("material name must match [a-z][a-z0-9_-]*"); }
      if (budgetOptions().indexOf(id.value) >= 0) { errors.push("budget id already declared"); }
      var capacity = { kind: "unlimited", value: null };
      if (capKind.value === "finite") {
        var value = numberOrNull(capValue.value);
        if (value === null || value < 0) { errors.push("ceiling must be a nonnegative decimal number"); }
        capacity = { kind: "finite", value: value };
      }
      if (errors.length) { message.className = "small err-text"; message.textContent = errors.join("; "); return; }
      proposed.budgets.push({
        id: id.value,
        material: { kind: kind.value, name: name.value, quality: kind.value === "item" ? "normal" : null },
        capacity: capacity
      });
      changed();
    });
    return form;
  }

  function selectedEndpointKeys() { return Object.keys(state.selEndpoints); }

  function feedForm() {
    var form = E("div", "card plain");
    add(form, E("div", null, "Declare a feed at the selected endpoint"));
    var keys = selectedEndpointKeys();
    add(form, E("p", "small", keys.length ? ("selected: " + keys.join(", "))
      : "Select a port, lane or inventory first (click the map, or a row in the Selection tab)."));
    var id = field(form, "feed id (token)", "feed_" + (A.feeds.length + 1), "feed_a");
    var budget = choice(form, "shared global budget id", budgetOptions().map(function (b) { return [b, b]; }), budgetOptions()[0]);
    var capKind = choice(form, "local feed ceiling", [["unlimited", "unlimited"], ["finite", "finite"]], "unlimited");
    var capValue = field(form, "local ceiling value (items/s)", "", "10");
    var message = add(form, E("p", "small"));
    var button = add(form, E("button", "act", "Declare feed"));
    button.addEventListener("click", function () {
      var errors = [];
      var target = selectedEndpointKeys();
      if (target.length !== 1) { errors.push("select exactly one endpoint to declare a feed"); }
      if (!TOKEN.test(id.value)) { errors.push("feed id must match [a-z][a-z0-9_-]*"); }
      if (!budget.value) { errors.push("declare a global budget first"); }
      if (A.feeds.some(function (f) { return f.id === id.value; })) { errors.push("feed id already used"); }
      var endpoint = target.length === 1 ? endpointByKey[target[0]] : null;
      if (endpoint && endpoint.kind === "port" && endpoint.role === "outgoing") {
        errors.push("a feed cannot target an outgoing port");
      }
      if (endpoint && A.feeds.some(function (f) { return epKey(f.endpoint) === endpoint.key && f.budget_id === budget.value; })) {
        errors.push("this endpoint already draws on that budget");
      }
      var capacity = { kind: "unlimited", value: null };
      if (capKind.value === "finite") {
        var value = numberOrNull(capValue.value);
        if (value === null || value < 0) { errors.push("ceiling must be a nonnegative decimal number"); }
        capacity = { kind: "finite", value: value };
      }
      if (errors.length || !endpoint) {
        message.className = "small err-text";
        message.textContent = errors.join("; ") || "no endpoint selected";
        return;
      }
      A.feeds.push({ id: id.value, budget_id: budget.value, endpoint: endpoint.id, capacity: capacity });
      changed();
    });
    return form;
  }

  function outletForm() {
    var form = E("div", "card plain");
    add(form, E("div", null, "Declare an export or surplus outlet at the selected endpoint"));
    var keys = selectedEndpointKeys();
    add(form, E("p", "small", keys.length ? ("selected: " + keys.join(", ")) : "Select one outgoing port, lane exit or inventory first."));
    var outlet = choice(form, "outlet kind", [["export", "export (net rate requirement)"], ["surplus", "surplus (declared removal)"]], "export");
    var id = field(form, "outlet id (token)", "", "product");
    var name = field(form, "material name", "", "iron-plate");
    var requirement = choice(form, "requirement", [["minimum", "minimum"], ["exact", "exact"]], "minimum");
    var rate = field(form, "net rate (items/s)", "0", "5");
    var service = field(form, "external removal service (required)", "", "continuous external removal");
    var sinkKind = choice(form, "sink ceiling", [["unlimited", "unlimited"], ["finite", "finite"]], "unlimited");
    var sinkValue = field(form, "sink ceiling value (items/s)", "", "20");
    var message = add(form, E("p", "small"));
    var button = add(form, E("button", "act", "Declare outlet"));
    button.addEventListener("click", function () {
      var errors = [];
      var target = selectedEndpointKeys();
      if (target.length !== 1) { errors.push("select exactly one endpoint"); }
      if (!TOKEN.test(id.value)) { errors.push("outlet id must match [a-z][a-z0-9_-]*"); }
      if (!TOKEN.test(name.value)) { errors.push("material name must match [a-z][a-z0-9_-]*"); }
      if (!service.value.trim()) { errors.push("an outlet needs an explicit ongoing external removal service"); }
      var endpoint = target.length === 1 ? endpointByKey[target[0]] : null;
      if (endpoint && endpoint.kind === "port" && endpoint.role === "incoming") {
        errors.push("an outlet cannot target an incoming port");
      }
      var value = numberOrNull(rate.value);
      if (outlet.value === "export" && (value === null || value < 0)) { errors.push("rate must be a nonnegative decimal number"); }
      var sink = { kind: "external", service: service.value, capacity: { kind: "unlimited", value: null } };
      if (sinkKind.value === "finite") {
        var ceiling = numberOrNull(sinkValue.value);
        if (ceiling === null || ceiling < 0) { errors.push("sink ceiling must be a nonnegative decimal number"); }
        sink.capacity = { kind: "finite", value: ceiling };
      }
      if (errors.length || !endpoint) {
        message.className = "small err-text";
        message.textContent = errors.join("; ") || "no endpoint selected";
        return;
      }
      var material = { kind: "item", name: name.value, quality: "normal" };
      if (outlet.value === "export") {
        proposed.exports.push({ id: id.value, material: material, endpoint: endpoint.id, requirement: requirement.value, rate: value, sink: sink });
      } else {
        proposed.surplus.push({ id: id.value, material: material, endpoint: endpoint.id, sink: sink });
      }
      changed();
    });
    return form;
  }

  /* ------------------------------------------------------- export /import */

  function draftDocument() {
    return {
      document_kind: D.document_kind,
      view_version: D.view_version,
      blueprint_hash: A.blueprint_hash,
      graph_hash: A.graph_hash,
      assignments: assignmentDoc(),
      proposed_request: {
        budgets: proposed.budgets,
        exports: proposed.exports,
        surplus: proposed.surplus,
        objective: proposed.objective
      },
      notes: [
        "Produced by the routing viewer for host reanalysis. The page ran no solver and wrote no file.",
        "Budgets, exports and surplus are request material; only 'assignments' is an AssignmentSet."
      ]
    };
  }

  var exportKindValue = "assignments";

  function renderIo(root) {
    add(root, E("h2", null, "Export"));
    add(root, E("p", "note", "The page produces JSON for the host to reanalyze. It never writes a file or solves anything by itself."));
    var kind = choice(root, "document", [["assignments", "AssignmentSet only"], ["draft", "Assignment draft with proposed budgets and outlets"]], exportKindValue);
    var area = add(root, E("textarea"));
    area.id = "export-text";
    area.spellcheck = false;
    function fill() {
      exportKindValue = kind.value;
      area.value = JSON.stringify(kind.value === "draft" ? draftDocument() : assignmentDoc(), null, 2);
    }
    kind.addEventListener("change", fill);
    fill();
    var refresh = add(root, E("button", "act sub", "Refresh"));
    refresh.addEventListener("click", fill);
    var download = add(root, E("button", "act", "Download"));
    download.addEventListener("click", function () {
      var blob = new Blob([area.value], { type: "application/json" });
      var url = URL.createObjectURL(blob);
      var link = E("a");
      link.href = url;
      link.download = (kind.value === "draft" ? "routing_assignment_draft.json" : "routing_assignments.json");
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
    });

    add(root, E("h2", null, "Import"));
    add(root, E("p", "note", "Reimport checks the blueprint and graph hashes and resolves every entity, endpoint, recipe and condition against this graph."));
    var input = add(root, E("textarea"));
    input.id = "import-text";
    input.spellcheck = false;
    input.value = state.importText || "";
    input.addEventListener("input", function () { state.importText = input.value; });
    var forceLabel = add(root, E("label", "field"));
    var force = add(forceLabel, E("input"));
    force.type = "checkbox";
    force.id = "import-force";
    add(forceLabel, E("span", null, "load anyway when the hashes are stale (keeps the document's hashes and marks the page stale)"));
    var button = add(root, E("button", "act", "Import assignments"));
    var message = add(root, E("p", "small"));
    message.id = "import-message";
    if (state.importMessage) {
      message.className = state.importOk ? "small" : "small err-text";
      message.textContent = state.importMessage;
    }
    button.addEventListener("click", function () {
      state.importText = input.value;
      applyImport(input.value, force.checked);
    });
  }

  function importReport(document_) {
    var set = document_;
    if (document_ && typeof document_ === "object" && document_.assignments
        && typeof document_.assignments === "object" && document_.assignments.feeds && !document_.feeds) {
      set = document_.assignments;
    }
    var stale = [], unknown = [];
    if (!set || typeof set !== "object" || !Array.isArray(set.feeds)) {
      return { set: null, stale: stale, unknown: ["document is not an assignment set"] };
    }
    if (set.blueprint_hash !== G.blueprint_hash) {
      stale.push("stale blueprint hash: document has " + dash(set.blueprint_hash) + ", this graph has " + dash(G.blueprint_hash));
    }
    if (set.graph_hash !== G.graph_hash) {
      stale.push("stale graph hash: document has " + dash(set.graph_hash) + ", this graph has " + dash(G.graph_hash));
    }
    set.feeds.forEach(function (feed) {
      var key = epKey(feed && feed.endpoint);
      var endpoint = endpointByKey[key];
      if (!endpoint) { unknown.push("unknown feed endpoint: " + key); return; }
      if (endpoint.kind === "port" && endpoint.role === "outgoing") { unknown.push("feed targets an outgoing port: " + key); }
    });
    (set.furnaces || []).forEach(function (furnace) {
      var key = entKey(furnace && furnace.entity);
      var entity = entityByKey[key];
      if (!entity) { unknown.push("unknown furnace entity: " + key); return; }
      if ((entity.furnace_candidates || []).indexOf(furnace.recipe) < 0) {
        unknown.push("recipe " + dash(furnace.recipe) + " is not a recorded candidate of " + key);
      }
    });
    (set.controls || []).forEach(function (control) {
      if ((G.conditions || []).indexOf(control && control.condition) < 0) {
        unknown.push("unknown control condition: " + dash(control && control.condition));
      }
    });
    return { set: set, stale: stale, unknown: unknown };
  }

  function applyImport(text, force) {
    var parsed;
    try { parsed = JSON.parse(text); }
    catch (error) {
      state.importOk = false;
      state.importMessage = "Not valid JSON: " + error.message;
      renderPanel();
      return;
    }
    var report = importReport(parsed);
    if (!report.set || report.unknown.length || (report.stale.length && !force)) {
      state.importOk = false;
      state.importMessage = "Not applied. " + report.stale.concat(report.unknown).join("; ")
        + (report.stale.length && !report.unknown.length ? " — tick 'load anyway' to inspect it as a stale document." : "");
      renderPanel();
      return;
    }
    A = copyAssignments(report.set);
    state.importOk = true;
    state.importMessage = "Imported " + A.feeds.length + " feed(s), " + A.furnaces.length + " furnace override(s), "
      + A.controls.length + " control assignment(s)."
      + (report.stale.length ? " Loaded with STALE hashes: " + report.stale.join("; ") : "");
    changed();
  }

  /* ------------------------------------------------------ selection panel */

  function keySet(keys) {
    var out = {};
    (keys || []).forEach(function (key) { out[key] = true; });
    return out;
  }

  function renderSelection(root) {
    add(root, E("h2", null, "Selection"));
    var entityKeys = Object.keys(state.selEntities);
    var endpointKeys = Object.keys(state.selEndpoints);
    if (!entityKeys.length && !endpointKeys.length) {
      add(root, E("p", "note", "Click an entity on the map, or a row in another tab. Shift-click adds to the selection."));
    }
    if (endpointKeys.length) {
      add(root, E("h2", null, "Selected endpoints (" + endpointKeys.length + ")"));
      var budgets = {};
      endpointKeys.forEach(function (key) {
        A.feeds.forEach(function (feed) {
          if (epKey(feed.endpoint) === key) { budgets[feed.budget_id] = (budgets[feed.budget_id] || 0) + 1; }
        });
      });
      Object.keys(budgets).forEach(function (id) {
        if (budgets[id] > 1) {
          add(root, E("p", "note", budgets[id] + " selected endpoints declare a feed on global budget '" + id
            + "'. They share that one ceiling; they do not each receive it."));
        }
      });
      endpointKeys.forEach(function (key) { add(root, endpointCard(key)); });
    }
    entityKeys.forEach(function (key) { add(root, entityCard(key)); });
    if (state.finding) {
      var finding = findingById[state.finding];
      if (finding) {
        add(root, E("h2", null, "Highlighted by the selected finding"));
        scopeLine(root, "entities", finding.highlight.entities);
        scopeLine(root, "endpoints", finding.highlight.endpoints);
        scopeLine(root, "arcs", finding.highlight.arcs);
      }
    }
  }

  function endpointCard(key) {
    var endpoint = endpointByKey[key];
    var card = E("div", "card plain");
    if (!endpoint) { add(card, E("p", "err-text", "unresolved endpoint " + key)); return card; }
    add(card, E("div", "mono", endpoint.key));
    kv(card, "kind", endpoint.kind);
    if (endpoint.role) { kv(card, "role", endpoint.role); }
    if (endpoint.side) { kv(card, "lane side", endpoint.side); }
    if (endpoint.position_text) { kv(card, "position", endpoint.position_text); }
    if (endpoint.direction_text) { kv(card, "direction", endpoint.direction_text); }
    kv(card, "eligibility", endpoint.eligibility_text);
    if (endpoint.storage_text) { kv(card, "storage", endpoint.storage_text); }
    if (endpoint.boundary_candidate !== undefined) { kv(card, "boundary candidate", endpoint.boundary_candidate ? "yes" : "no"); }
    if (endpoint.incoming_key) { kv(card, "lane entrance", endpoint.incoming_key); }
    if (endpoint.outgoing_key) { kv(card, "lane exit", endpoint.outgoing_key); }
    scopeLine(card, "evidence", endpoint.evidence_ids);
    var feeds = A.feeds.filter(function (f) { return epKey(f.endpoint) === key; });
    feeds.forEach(function (feed) { kv(card, "declared feed", feed.id + " on budget " + feed.budget_id + " (" + capacityText(feed.capacity) + ")"); });
    extras(card, endpoint.extra, "Additional endpoint fields");
    var drop = add(card, E("button", "act sub", "Deselect"));
    drop.addEventListener("click", function () { delete state.selEndpoints[key]; renderPanel(); request(); });
    return card;
  }

  function entityCard(key) {
    var entity = entityByKey[key];
    var card = E("div", "card plain");
    if (!entity) { add(card, E("p", "err-text", "unresolved entity " + key)); return card; }
    add(card, E("div", "mono", entity.key));
    kv(card, "prototype", entity.prototype);
    kv(card, "position", entity.position_text);
    kv(card, "direction", entity.direction_text);
    kv(card, "orientation", entity.orientation_text);
    kv(card, "quality", entity.quality);
    kv(card, "support", entity.support);
    if (entity.subsystem) { kv(card, "subsystem", entity.subsystem); }
    if (entity.mod) { kv(card, "mod", entity.mod); }
    if (entity.furnace_candidates.length) { kv(card, "furnace candidates", entity.furnace_candidates.join(", ")); }
    scopeLine(card, "evidence", entity.evidence_ids);
    extras(card, entity.extra, "Additional entity fields");
    [["ports", entity.ports], ["lanes", entity.lanes], ["inventories", entity.inventories]].forEach(function (pair) {
      if (!pair[1].length) { return; }
      add(card, E("p", "small", pair[0] + ":"));
      pair[1].forEach(function (endpointKey) {
        var endpoint = endpointByKey[endpointKey];
        var row = add(card, E("div", "row" + (state.selEndpoints[endpointKey] ? " sel" : "")));
        add(row, E("span", "mono", endpoint ? endpoint.name : endpointKey));
        add(row, E("span", "grow small", endpoint ? (endpoint.role || endpoint.side || endpoint.kind) + " · " + endpoint.eligibility_text : "?"));
        var pick = add(row, E("button", "mini", state.selEndpoints[endpointKey] ? "deselect" : "select"));
        pick.addEventListener("click", function () {
          if (state.selEndpoints[endpointKey]) { delete state.selEndpoints[endpointKey]; }
          else { state.selEndpoints[endpointKey] = true; }
          renderPanel(); request();
        });
      });
    });
    if (entity.arcs.length) {
      add(card, E("p", "small", "arcs touching this entity:"));
      entity.arcs.forEach(function (arcId) {
        var arc = arcById[arcId];
        var row = add(card, E("div", "row"));
        add(row, E("span", "mono", arcId));
        add(row, E("span", "grow small", arc ? (arc.semantics + " · " + arc.eligibility_text
          + (arc.conditions.length ? " · conditions: " + arc.conditions.join(", ") : "")) : "?"));
      });
    }
    add(card, E("p", "small", "original blueprint record (inert text):"));
    add(card, E("pre", "raw", entity.raw_text));
    var drop = add(card, E("button", "act sub", "Deselect"));
    drop.addEventListener("click", function () { delete state.selEntities[key]; renderPanel(); request(); });
    return card;
  }

  /* ------------------------------------------------------------ selection */

  function selectFinding(id) {
    var finding = findingById[id];
    if (!finding) { return; }
    state.finding = (state.finding === id) ? null : id;
    if (state.finding) {
      HL = {
        entities: keySet(finding.highlight.entities),
        endpoints: keySet(finding.highlight.endpoints),
        arcs: keySet(finding.highlight.arcs)
      };
      if (finding.focus) { focusBox(finding.focus); }
    } else {
      HL = { entities: {}, endpoints: {}, arcs: {} };
    }
    renderPanel();
    request();
  }

  function selectEntity(key, additive) {
    if (!additive) { state.selEntities = {}; state.selEndpoints = {}; }
    state.selEntities[key] = true;
    state.tab = "selection";
    renderPanel();
    request();
  }

  function focusKeys(entityKeys, endpointKeys, arcIds) {
    var xs = [], ys = [];
    (entityKeys || []).forEach(function (key) {
      var entity = entityByKey[key];
      if (entity) { xs.push(entity.box[0], entity.box[2]); ys.push(entity.box[1], entity.box[3]); }
    });
    (endpointKeys || []).forEach(function (key) {
      var endpoint = endpointByKey[key];
      if (!endpoint) { return; }
      var points = endpoint.polyline && endpoint.polyline.length ? endpoint.polyline : [endpoint.anchor];
      points.forEach(function (point) { xs.push(point[0]); ys.push(point[1]); });
    });
    (arcIds || []).forEach(function (id) {
      var arc = arcById[id];
      if (arc) { xs.push(arc.geometry[0], arc.geometry[2]); ys.push(arc.geometry[1], arc.geometry[3]); }
    });
    if (!xs.length) { return; }
    focusBox([Math.min.apply(null, xs), Math.min.apply(null, ys), Math.max.apply(null, xs), Math.max.apply(null, ys)]);
  }

  /* ---------------------------------------------------------------- canvas */

  var ctx = canvas.getContext("2d");
  var view = { cx: 0, cy: 0, k: 8 };
  var pending = false;
  var drawn = { entities: 0, arcs: 0 };

  function palette() {
    var dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    return dark
      ? { entity: "#2b3341", line: "#57657d", odd: "#4a3520", oddLine: "#e0b33c", lane: "#6f819d",
          arc: "#8fa6c9", hl: "#ffd257", sel: "#7fb0ff", text: "#e9ecf1" }
      : { entity: "#dfe4ec", line: "#8c98ad", odd: "#f6e2b8", oddLine: "#a97b00", lane: "#7d8ba1",
          arc: "#4a5b78", hl: "#b8570a", sel: "#1c4f9c", text: "#16181d" };
  }
  var C = palette();
  if (window.matchMedia) {
    var media = window.matchMedia("(prefers-color-scheme: dark)");
    if (media.addEventListener) { media.addEventListener("change", function () { C = palette(); request(); }); }
  }

  function request() {
    if (pending) { return; }
    pending = true;
    window.requestAnimationFrame(draw);
  }

  function fit(box) {
    var w = canvas.clientWidth || 800, h = canvas.clientHeight || 600;
    var width = Math.max(box[2] - box[0], 1e-6), height = Math.max(box[3] - box[1], 1e-6);
    view.k = Math.min(w / (width * 1.15), h / (height * 1.15));
    view.k = Math.max(Math.min(view.k, 64), 0.02);
    view.cx = (box[0] + box[2]) / 2;
    view.cy = (box[1] + box[3]) / 2;
    request();
  }
  function focusBox(box) {
    var padded = [box[0] - 1.5, box[1] - 1.5, box[2] + 1.5, box[3] + 1.5];
    fit(padded);
  }

  function draw() {
    pending = false;
    var w = canvas.clientWidth, h = canvas.clientHeight;
    var dpr = window.devicePixelRatio || 1;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    var k = view.k;
    var ox = w / 2 - view.cx * k, oy = h / 2 - view.cy * k;
    var x0 = -ox / k, x1 = (w - ox) / k, y0 = -oy / k, y1 = (h - oy) / k;
    var entities = G.entities || [], arcs = G.arcs || [], lanes = G.lanes || [];
    var i, item, box;

    var normal = [], odd = [];
    drawn.entities = 0;
    for (i = 0; i < entities.length; i++) {
      item = entities[i];
      box = item.box;
      if (box[2] < x0 || box[0] > x1 || box[3] < y0 || box[1] > y1) { continue; }
      (item.support === "supported" ? normal : odd).push(item);
      drawn.entities++;
    }
    function fillBoxes(items, fillStyle, strokeStyle, dashPattern) {
      if (!items.length) { return; }
      ctx.beginPath();
      for (var j = 0; j < items.length; j++) {
        var b = items[j].box;
        ctx.rect(b[0] * k + ox, b[1] * k + oy, (b[2] - b[0]) * k, (b[3] - b[1]) * k);
      }
      ctx.fillStyle = fillStyle;
      ctx.fill();
      if (k > 2) {
        ctx.setLineDash(dashPattern || []);
        ctx.lineWidth = 1;
        ctx.strokeStyle = strokeStyle;
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }
    fillBoxes(normal, C.entity, C.line, null);
    fillBoxes(odd, C.odd, C.oddLine, [4, 3]);

    if (k > 1.5) {
      ctx.beginPath();
      for (i = 0; i < lanes.length; i++) {
        var points = lanes[i].polyline;
        if (!points.length) { continue; }
        if (points[0][0] * k + ox < -50 || points[0][0] * k + ox > w + 50
          || points[0][1] * k + oy < -50 || points[0][1] * k + oy > h + 50) { continue; }
        ctx.moveTo(points[0][0] * k + ox, points[0][1] * k + oy);
        for (var p = 1; p < points.length; p++) { ctx.lineTo(points[p][0] * k + ox, points[p][1] * k + oy); }
      }
      ctx.strokeStyle = C.lane;
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    var styles = { exact: [], conditional: [], relaxed: [] };
    drawn.arcs = 0;
    for (i = 0; i < arcs.length; i++) {
      var geometry = arcs[i].geometry;
      var ax = geometry[0] * k + ox, ay = geometry[1] * k + oy;
      var bx = geometry[2] * k + ox, by = geometry[3] * k + oy;
      if ((ax < -50 && bx < -50) || (ax > w + 50 && bx > w + 50) || (ay < -50 && by < -50) || (ay > h + 50 && by > h + 50)) { continue; }
      (styles[arcs[i].semantics] || styles.exact).push([ax, ay, bx, by]);
      drawn.arcs++;
    }
    function strokeSegments(segments, dashPattern, width) {
      if (!segments.length) { return; }
      ctx.beginPath();
      for (var j = 0; j < segments.length; j++) {
        ctx.moveTo(segments[j][0], segments[j][1]);
        ctx.lineTo(segments[j][2], segments[j][3]);
      }
      ctx.setLineDash(dashPattern);
      ctx.lineWidth = width;
      ctx.strokeStyle = C.arc;
      ctx.stroke();
      ctx.setLineDash([]);
    }
    strokeSegments(styles.exact, [], 1.5);
    strokeSegments(styles.conditional, [5, 4], 1.5);
    strokeSegments(styles.relaxed, [1, 3], 1.5);

    /* highlight and selection overlays: thick outline plus corner ticks, so they
       remain visible without relying on hue */
    function outline(box2, colour, width, dashPattern) {
      ctx.setLineDash(dashPattern || []);
      ctx.lineWidth = width;
      ctx.strokeStyle = colour;
      ctx.strokeRect(box2[0] * k + ox - 3, box2[1] * k + oy - 3,
        (box2[2] - box2[0]) * k + 6, (box2[3] - box2[1]) * k + 6);
      ctx.setLineDash([]);
    }
    Object.keys(HL.entities).forEach(function (key) {
      var entity = entityByKey[key];
      if (entity) { outline(entity.box, C.hl, 4, null); marker(entity.box, C.hl); }
    });
    Object.keys(state.selEntities).forEach(function (key) {
      var entity = entityByKey[key];
      if (entity) { outline(entity.box, C.sel, 2.5, [6, 4]); }
    });
    function strokeEndpoint(key, colour, width, dashPattern) {
      var endpoint = endpointByKey[key];
      if (!endpoint) { return; }
      ctx.setLineDash(dashPattern || []);
      ctx.lineWidth = width;
      ctx.strokeStyle = colour;
      if (endpoint.polyline && endpoint.polyline.length > 1) {
        ctx.beginPath();
        ctx.moveTo(endpoint.polyline[0][0] * k + ox, endpoint.polyline[0][1] * k + oy);
        for (var p = 1; p < endpoint.polyline.length; p++) {
          ctx.lineTo(endpoint.polyline[p][0] * k + ox, endpoint.polyline[p][1] * k + oy);
        }
        ctx.stroke();
      } else {
        ctx.beginPath();
        ctx.arc(endpoint.anchor[0] * k + ox, endpoint.anchor[1] * k + oy, Math.max(4, 0.18 * k), 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.setLineDash([]);
    }
    Object.keys(HL.endpoints).forEach(function (key) { strokeEndpoint(key, C.hl, 5, null); });
    Object.keys(state.selEndpoints).forEach(function (key) { strokeEndpoint(key, C.sel, 3, [6, 4]); });
    Object.keys(HL.arcs).forEach(function (id) {
      var arc = arcById[id];
      if (!arc) { return; }
      ctx.beginPath();
      ctx.moveTo(arc.geometry[0] * k + ox, arc.geometry[1] * k + oy);
      ctx.lineTo(arc.geometry[2] * k + ox, arc.geometry[3] * k + oy);
      ctx.lineWidth = 5;
      ctx.strokeStyle = C.hl;
      ctx.stroke();
      arrow(arc.geometry, k, ox, oy, C.hl);
    });

    if (k >= 14 && drawn.entities <= 300) {
      ctx.fillStyle = C.text;
      ctx.font = "11px system-ui, sans-serif";
      /* only label an entity when its own footprint gives the text room, so
         neighbouring labels cannot overprint each other */
      var labelled = normal.concat(odd);
      for (i = 0; i < labelled.length; i++) {
        var entity = labelled[i];
        var caption = entity.prototype + (entity.support === "supported" ? "" : " (" + entity.support + ")");
        var room = (entity.box[2] - entity.box[0]) * k + 6;
        if (ctx.measureText(caption).width > room) { continue; }
        ctx.fillText(caption, entity.box[0] * k + ox + 2, entity.box[1] * k + oy - 3);
      }
    }

    statusBar.textContent = "zoom ×" + view.k.toFixed(2) + " · centre " + view.cx.toFixed(1) + ", " + view.cy.toFixed(1)
      + " · drawing " + drawn.entities + "/" + entities.length + " entities, " + drawn.arcs + "/" + arcs.length + " arcs";
  }

  function marker(box, colour) {
    var k = view.k;
    var w = canvas.clientWidth, h = canvas.clientHeight;
    var ox = w / 2 - view.cx * k, oy = h / 2 - view.cy * k;
    var cx = (box[0] + box[2]) / 2 * k + ox, cy = (box[1] + box[3]) / 2 * k + oy;
    ctx.strokeStyle = colour;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cx - 14, cy); ctx.lineTo(cx - 6, cy);
    ctx.moveTo(cx + 6, cy); ctx.lineTo(cx + 14, cy);
    ctx.moveTo(cx, cy - 14); ctx.lineTo(cx, cy - 6);
    ctx.moveTo(cx, cy + 6); ctx.lineTo(cx, cy + 14);
    ctx.stroke();
  }

  function arrow(geometry, k, ox, oy, colour) {
    var ax = geometry[0] * k + ox, ay = geometry[1] * k + oy;
    var bx = geometry[2] * k + ox, by = geometry[3] * k + oy;
    var dx = bx - ax, dy = by - ay;
    var length = Math.sqrt(dx * dx + dy * dy);
    if (length < 6) { return; }
    dx /= length; dy /= length;
    ctx.beginPath();
    ctx.moveTo(bx, by);
    ctx.lineTo(bx - dx * 9 - dy * 5, by - dy * 9 + dx * 5);
    ctx.lineTo(bx - dx * 9 + dy * 5, by - dy * 9 - dx * 5);
    ctx.closePath();
    ctx.fillStyle = colour;
    ctx.fill();
  }

  /* ------------------------------------------------------------- controls */

  function toolButton(labelText, handler) {
    var button = add(tools, E("button", null, labelText));
    button.addEventListener("click", handler);
    return button;
  }
  toolButton("Fit all", function () { fit(G.bounds_box); });
  toolButton("Zoom in", function () { view.k = Math.min(view.k * 1.4, 400); request(); });
  toolButton("Zoom out", function () { view.k = Math.max(view.k / 1.4, 0.02); request(); });
  toolButton("Focus selection", function () {
    focusKeys(Object.keys(state.selEntities).concat(Object.keys(HL.entities)),
      Object.keys(state.selEndpoints).concat(Object.keys(HL.endpoints)),
      Object.keys(HL.arcs));
  });
  toolButton("Legend", function () { legend.hidden = !legend.hidden; });
  toolButton("Clear highlight", function () {
    HL = { entities: {}, endpoints: {}, arcs: {} };
    state.finding = null;
    state.selEntities = {};
    state.selEndpoints = {};
    renderPanel();
    request();
  });

  legend.textContent = "";
  add(legend, E("div", null, "solid outline = exact arc"));
  add(legend, E("div", null, "dashed outline = conditional arc or entity"));
  add(legend, E("div", null, "dotted = relaxed arc"));
  add(legend, E("div", null, "thick ring + cross ticks = finding evidence"));
  add(legend, E("div", null, "dashed ring = your selection"));
  add(legend, E("div", "small", "Drag to pan, wheel to zoom, click an entity to inspect."));

  var dragging = false, lastX = 0, lastY = 0, moved = 0;
  canvas.addEventListener("pointerdown", function (event) {
    dragging = true; moved = 0; lastX = event.clientX; lastY = event.clientY;
    canvas.classList.add("drag");
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", function (event) {
    if (!dragging) { return; }
    var dx = event.clientX - lastX, dy = event.clientY - lastY;
    moved += Math.abs(dx) + Math.abs(dy);
    lastX = event.clientX; lastY = event.clientY;
    view.cx -= dx / view.k;
    view.cy -= dy / view.k;
    request();
  });
  canvas.addEventListener("pointerup", function (event) {
    dragging = false;
    canvas.classList.remove("drag");
    if (moved < 4) { pick(event, event.shiftKey); }
  });
  canvas.addEventListener("pointercancel", function () { dragging = false; canvas.classList.remove("drag"); });
  canvas.addEventListener("wheel", function (event) {
    event.preventDefault();
    var rect = canvas.getBoundingClientRect();
    var mx = event.clientX - rect.left, my = event.clientY - rect.top;
    var before = screenToWorld(mx, my);
    var factor = Math.pow(1.0015, -event.deltaY);
    view.k = Math.max(0.02, Math.min(400, view.k * factor));
    var after = screenToWorld(mx, my);
    view.cx += before[0] - after[0];
    view.cy += before[1] - after[1];
    request();
  }, { passive: false });

  function screenToWorld(mx, my) {
    var w = canvas.clientWidth, h = canvas.clientHeight;
    return [(mx - w / 2) / view.k + view.cx, (my - h / 2) / view.k + view.cy];
  }

  function pick(event, additive) {
    var rect = canvas.getBoundingClientRect();
    var point = screenToWorld(event.clientX - rect.left, event.clientY - rect.top);
    var tolerance = Math.max(0.12, 6 / view.k);
    var endpoints = [].concat(G.ports || [], G.inventories || []);
    if (view.k >= 10) {
      for (var i = endpoints.length - 1; i >= 0; i--) {
        var anchor = endpoints[i].anchor;
        if (Math.abs(anchor[0] - point[0]) <= tolerance && Math.abs(anchor[1] - point[1]) <= tolerance) {
          if (!additive) { state.selEndpoints = {}; state.selEntities = {}; }
          state.selEndpoints[endpoints[i].key] = true;
          state.tab = "selection";
          renderPanel(); request();
          return;
        }
      }
    }
    var entities = G.entities || [];
    for (var j = entities.length - 1; j >= 0; j--) {
      var box = entities[j].box;
      if (point[0] >= box[0] && point[0] <= box[2] && point[1] >= box[1] && point[1] <= box[3]) {
        selectEntity(entities[j].key, additive);
        return;
      }
    }
    if (!additive) {
      state.selEntities = {}; state.selEndpoints = {};
      renderPanel(); request();
    }
  }

  function changed() {
    renderBanners();
    renderPanel();
    request();
  }

  if (window.ResizeObserver) {
    new window.ResizeObserver(function () { request(); }).observe(stage);
  } else {
    window.addEventListener("resize", request);
  }

  renderHeader();
  renderPanel();
  fit(G.bounds_box || [-1, -1, 1, 1]);

  /* Read-only hook for host-side interaction checks. */
  window.factoribotView = {
    model: D,
    highlight: function () {
      return { entities: Object.keys(HL.entities), endpoints: Object.keys(HL.endpoints), arcs: Object.keys(HL.arcs) };
    },
    selection: function () {
      return { entities: Object.keys(state.selEntities), endpoints: Object.keys(state.selEndpoints), finding: state.finding };
    },
    assignments: function () { return assignmentDoc(); },
    draft: draftDocument,
    stale: staleReport,
    selectFinding: selectFinding,
    importDocument: applyImport,
    viewport: function () { return { k: view.k, cx: view.cx, cy: view.cy, drawn: drawn }; },
    redraw: function () { draw(); }
  };
}());
