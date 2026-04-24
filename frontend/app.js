const STAGE_ORDER = ["ad", "landing_a", "landing_b", "structure", "price", "checkout", "item"];
const STAGE_LABELS = {
  ad: "Native Ad",
  landing_a: "Landing Page A",
  landing_b: "Landing Page B",
  structure: "Structure / Offer",
  price: "Price Page",
  checkout: "Checkout",
  item: "Item / Product",
};

// Rough per-1M-token pricing for cost estimation (USD)
const MODEL_PRICING = {
  "claude-opus-4-7":          { input: 15.0, output: 75.0, cacheRead: 1.50 },
  "claude-sonnet-4-6":        { input: 3.0,  output: 15.0, cacheRead: 0.30 },
  "claude-haiku-4-5-20251001":{ input: 0.80, output: 4.0,  cacheRead: 0.08 },
};

function uid() { return "s" + Math.random().toString(36).slice(2, 9); }

function defaultStage(kind, enabled) {
  return {
    uid: uid(),
    kind,
    enabled: !!enabled,
    label: "",
    url: "",
    text: "",
    notes: "",
    screenshot_base64: null,
    screenshot_media_type: null,
    inputMode: "url",
    preview_ok: false,
    preview_words: 0,
    preview_error: "",
    previewing: false,
    abVariant: false,
  };
}

function emptyCampaign(label) {
  return {
    label,
    product: { name: "", description: "", target_audience: "", price: "", vertical: "e-commerce / physical products" },
    ad: { headline: "", body: "", cta: "", image_description: "", image_base64: null, image_media_type: null },
    stages: [
      defaultStage("ad", true),
      defaultStage("landing_a", true),
      defaultStage("price", true),
      defaultStage("checkout", true),
    ],
  };
}

function app() {
  return {
    view: "setup",
    reportTab: "exec",
    health: null,
    personas: [],
    builtInPersonas: [],
    customCounter: 0,
    campaignA: emptyCampaign("A"),
    campaignB: emptyCampaign("B"),
    abEnabled: false,
    selectedModel: "claude-opus-4-7",
    customOllamaModel: "",
    concurrency: 4,
    running: false,
    errorMsg: "",
    result: null,
    lastRunModel: "",
    lastRunAt: null,
    showAbDetails: false,
    activeCampaign: "A",
    selectedPersonaId: null,
    menuOpen: false,
    personaModalOpen: false,
    personaSearch: "",
    savedSetups: [],
    savedRuns: [],

    async init() {
      try {
        this.health = await fetch("/api/health").then((r) => r.json());
        if (this.health?.default_model) this.selectedModel = this.health.default_model;
      } catch (e) {}
      try {
        const p = await fetch("/api/personas").then((r) => r.json());
        this.builtInPersonas = p.personas;
        this.resetPersonas();
      } catch (e) {
        this.errorMsg = "Failed to load personas.";
      }
      this.refreshStorage();
    },

    // ================= PERSONAS =================
    resetPersonas() {
      this.personas = this.builtInPersonas.map((p, i) => ({
        id: p.id,
        name: p.name,
        archetype: p.archetype,
        character_sheet: p.character_sheet,
        icon: p.icon || "👤",
        selected: i < 6,
        editing: false,
      }));
      this.customCounter = 0;
    },
    addCustomPersona() {
      this.customCounter += 1;
      this.personas.push({
        id: "custom_" + Date.now() + "_" + this.customCounter,
        name: "New persona",
        archetype: "",
        character_sheet: "",
        icon: "👤",
        selected: true,
        editing: true,
      });
    },
    deletePersona(idx) { this.personas.splice(idx, 1); },
    selectedCount() { return this.personas.filter((p) => p.selected).length; },
    shortDesc(sheet) {
      if (!sheet) return "";
      const s = sheet.trim();
      return s.length > 90 ? s.slice(0, 90) + "…" : s;
    },
    personaIconClass(i) {
      const classes = ["", "blue", "green", "pink", "purple"];
      return classes[i % classes.length];
    },
    personaIconFor(id) {
      const p = this.personas.find((x) => x.id === id);
      return p?.icon || "👤";
    },

    // ================= STAGES =================
    stageDefaultLabel(kind) {
      return STAGE_LABELS[kind] || "Stage";
    },
    addStage() {
      // pick first unused kind; if all are used, fall back to landing_b
      const used = new Set(this.campaignA.stages.map((s) => s.kind));
      const next = STAGE_ORDER.find((k) => !used.has(k)) || "landing_b";
      this.campaignA.stages.push(defaultStage(next, true));
    },
    removeStage(i) {
      this.campaignA.stages.splice(i, 1);
    },
    async previewStage(stage) {
      stage.preview_error = "";
      stage.preview_ok = false;
      stage.preview_words = 0;
      if (!stage.url) return;
      stage.previewing = true;
      try {
        const r = await fetch("/api/preview_stage", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: stage.url }),
        });
        const j = await r.json();
        if (j.ok && j.word_count > 0) {
          stage.preview_ok = true;
          stage.preview_words = j.word_count;
        } else {
          stage.preview_error = (j.text || "").slice(0, 160) || "Fetched but no usable text extracted.";
        }
      } catch (e) {
        stage.preview_error = "Preview failed: " + (e?.message || e);
      } finally {
        stage.previewing = false;
      }
    },

    // ================= IMAGES =================
    async onAdImage(ev, campaign) {
      const f = ev.target.files[0];
      if (!f) return;
      const b64 = await fileToBase64(f);
      campaign.ad.image_base64 = b64;
      campaign.ad.image_media_type = f.type || "image/png";
    },
    async onStageImage(ev, stage) {
      const f = ev.target.files[0];
      if (!f) return;
      const b64 = await fileToBase64(f);
      stage.screenshot_base64 = b64;
      stage.screenshot_media_type = f.type || "image/png";
    },

    // ================= CONFIG =================
    onModelChange() {
      if (this.selectedModel !== "__ollama_custom__" && this.selectedModel.startsWith("ollama:")) {
        this.customOllamaModel = "";
      }
    },
    effectiveModel() {
      if (this.selectedModel === "__ollama_custom__") {
        return this.customOllamaModel.startsWith("ollama:")
          ? this.customOllamaModel
          : "ollama:" + this.customOllamaModel;
      }
      return this.selectedModel;
    },
    modelDisplayName() {
      const m = this.lastRunModel || this.effectiveModel();
      if (m.startsWith("ollama:")) return "Ollama: " + m.slice("ollama:".length);
      if (m.includes("opus")) return "Claude Opus";
      if (m.includes("sonnet")) return "Claude Sonnet";
      if (m.includes("haiku")) return "Claude Haiku";
      return m;
    },
    estimatedCalls() {
      const enabled = this.campaignA.stages.filter((s) => s.enabled).length;
      const campaigns = this.abEnabled ? 2 : 1;
      const calls = this.selectedCount() * (enabled + 1) * campaigns;
      return `~${calls}`;
    },

    // ================= VALIDATION & RUN =================
    canRun() {
      if (this.selectedCount() === 0) return false;
      const badPersona = this.personas.find((p) => p.selected && !p.character_sheet.trim());
      if (badPersona) return false;
      if (!this.campaignA.product.name) return false;
      if (!this.campaignA.ad.headline) return false;
      if (!this.campaignA.stages.some((s) => s.enabled)) return false;
      if (this.selectedModel === "__ollama_custom__" && !this.customOllamaModel.trim()) return false;
      return true;
    },
    _enabledStagesPayload(campaign) {
      return campaign.stages
        .filter((s) => s.enabled)
        .map((s) => ({
          kind: s.kind,
          label: s.label || null,
          url: s.url || null,
          text: s.text || null,
          screenshot_base64: s.screenshot_base64 || null,
          screenshot_media_type: s.screenshot_media_type || null,
          notes: s.notes || null,
        }));
    },
    _prepareCampaignB() {
      const base = JSON.parse(JSON.stringify(this.campaignA));
      base.label = "B";
      base.stages = JSON.parse(JSON.stringify(this.campaignA.stages));
      const b = this.campaignB;
      if (b.ad.headline) base.ad.headline = b.ad.headline;
      if (b.ad.body) base.ad.body = b.ad.body;
      if (b.ad.cta) base.ad.cta = b.ad.cta;
      if (b.ad.image_base64) {
        base.ad.image_base64 = b.ad.image_base64;
        base.ad.image_media_type = b.ad.image_media_type;
      }
      if (b.product.price) base.product.price = b.product.price;
      return base;
    },
    async run() {
      this.errorMsg = "";
      this.running = true;
      try {
        const model = this.effectiveModel();
        const campaignA = JSON.parse(JSON.stringify(this.campaignA));
        campaignA.label = "A";
        campaignA.stages = this._enabledStagesPayload(this.campaignA);
        const campaigns = [campaignA];
        if (this.abEnabled) {
          const b = this._prepareCampaignB();
          b.stages = this._enabledStagesPayload({ stages: b.stages });
          campaigns.push(b);
        }
        const payload = {
          campaigns,
          model,
          concurrency: this.concurrency,
          personas: this.personas
            .filter((p) => p.selected)
            .map((p) => ({
              id: p.id,
              name: p.name,
              archetype: p.archetype,
              character_sheet: p.character_sheet,
              icon: p.icon || null,
            })),
        };
        const r = await fetch("/api/simulate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!r.ok) {
          const err = await r.json().catch(() => ({ detail: r.statusText }));
          throw new Error(err.detail || "Request failed");
        }
        this.result = await r.json();
        this.lastRunModel = model;
        this.lastRunAt = new Date();
        this.reportTab = "exec";
        this.activeCampaign = this.result.reports?.[0]?.campaign_label || "A";
        this.selectedPersonaId = this.result.reports?.[0]?.personas?.[0]?.persona_id || null;
        this._saveRunToHistory();
        this.view = "report";
      } catch (e) {
        this.errorMsg = e.message || String(e);
      } finally {
        this.running = false;
      }
    },

    // ================= DEMO =================
    loadDemo() {
      this.campaignA = {
        label: "A",
        product: {
          name: "AuroraGlow LED Sunrise Alarm",
          description: "A bedside alarm that simulates a 30-minute sunrise to wake you naturally, replacing jarring alarms. Bluetooth speaker, FM radio, USB-C charging, 20 light modes.",
          target_audience: "25-45 urban professionals with poor sleep quality who already use wellness apps",
          price: "$79 (normally $119, free shipping over $50)",
          vertical: "e-commerce / physical products",
        },
        ad: {
          headline: "The Alarm That Wakes You With Sunlight, Not Sound",
          body: "Thousands of light sleepers finally wake up without dread. 30-min sunrise simulation. Free US shipping.",
          cta: "See how it works",
          image_description: "Warm sunrise light through bedroom curtains",
          image_base64: null,
          image_media_type: null,
        },
        stages: [
          {
            ...defaultStage("ad", true),
            label: "Native Ad (Main Creative)",
          },
          {
            ...defaultStage("landing_a", true),
            label: "Landing Page A (Main Offer)",
            inputMode: "text",
            text: "Finally, a morning that doesn't feel like a punishment. AuroraGlow mimics the real sunrise over 30 minutes so your body wakes naturally. 4.8 stars from 2,400 reviews. Watch our 90-second demo.",
          },
          {
            ...defaultStage("structure", true),
            label: "Structure / Offer Page",
            inputMode: "text",
            text: "What's in the box: AuroraGlow unit, USB-C cable, magnetic base, setup card. Specs: 20 light modes, Bluetooth 5.3 speaker, FM radio, 7-day programmable alarms, touch + app control. Warranty: 2 years. Ships in 2-3 days.",
          },
          {
            ...defaultStage("price", true),
            label: "Price Page",
            inputMode: "text",
            text: "AuroraGlow LED Sunrise Alarm — $79 (was $119, save $40). Subscribe to the newsletter and save another $10 on your next order. Free US shipping. Sleep Bundle: add the pillow mist for $19 more.",
          },
          {
            ...defaultStage("checkout", true),
            label: "Checkout Page",
            inputMode: "text",
            text: "Cart: AuroraGlow x 1 — $79. Shipping: Free. Tax: calculated next step. Total: $79. Guest checkout available. Apple Pay / Google Pay / PayPal.",
          },
        ],
      };
    },

    // ================= REPORT HELPERS =================
    firstReport() { return this.result?.reports?.[0]; },
    activeReport() {
      const reports = this.result?.reports || [];
      return reports.find((r) => r.campaign_label === this.activeCampaign) || reports[0];
    },
    selectedPersona() {
      const r = this.activeReport();
      if (!r || !this.selectedPersonaId) return null;
      return r.personas.find((p) => p.persona_id === this.selectedPersonaId) || r.personas[0];
    },
    convertedOver() {
      const r = this.activeReport() || this.firstReport();
      if (!r) return "0/0";
      const n = r.personas.length;
      const converted = r.personas.filter((p) => p.converted).length;
      return `${converted}/${n}`;
    },
    formatKTokens() {
      const u = this.result?.token_usage || {};
      const total = (u.input_tokens || 0) + (u.output_tokens || 0) + (u.cache_read_input_tokens || 0) + (u.cache_creation_input_tokens || 0);
      if (total < 1000) return total.toString();
      if (total < 1e6) return Math.round(total / 1000) + "k";
      return (total / 1e6).toFixed(1) + "M";
    },
    approxCost() {
      const u = this.result?.token_usage || {};
      const model = this.lastRunModel || "";
      if (model.startsWith("ollama:")) return "0.00";
      const p = MODEL_PRICING[model];
      if (!p) return "—";
      const inp = (u.input_tokens || 0) + (u.cache_creation_input_tokens || 0);
      const cr = u.cache_read_input_tokens || 0;
      const out = u.output_tokens || 0;
      const cost = (inp / 1e6) * p.input + (cr / 1e6) * p.cacheRead + (out / 1e6) * p.output;
      return cost.toFixed(2);
    },
    funnelBarPct(stage) {
      const r = this.activeReport();
      const n = r?.personas?.length || 1;
      if (stage.entered === 0) return 8;
      const pct = (stage.continued / n) * 100;
      return Math.max(pct, 6);
    },
    funnelBarClass(stage, i) {
      if (stage.entered === 0) return "skipped";
      if (i === 0) return "";
      return "step-" + Math.min(i, 4);
    },
    dimensionScores() {
      const r = this.activeReport();
      if (!r) return null;
      const sums = { clarity: 0, trust: 0, price_fit: 0, urgency: 0, cta: 0 };
      let n = 0;
      for (const p of r.personas) {
        for (const s of p.stages) {
          sums.clarity += s.scores.clarity;
          sums.trust += s.scores.trust;
          sums.price_fit += s.scores.price_fit;
          sums.urgency += s.scores.urgency;
          sums.cta += s.scores.cta;
          n += 1;
        }
      }
      if (n === 0) return null;
      const labels = {
        clarity: "Clarity",
        trust: "Trust",
        price_fit: "Price fit",
        urgency: "Urgency",
        cta: "CTA",
      };
      const rows = Object.keys(sums).map((k) => {
        const v = sums[k] / n;
        const band = v < 4 ? "score-low" : v < 7 ? "score-mid" : "score-high";
        return { key: k, label: labels[k], value: v, band };
      });
      rows.sort((a, b) => a.value - b.value);
      return rows;
    },
    weakestDimensionHint() {
      const rows = this.dimensionScores();
      if (!rows || rows.length === 0) return "";
      const weakest = rows[0];
      if (weakest.value >= 7) return "Solid across all dimensions.";
      return `Weakest dimension: ${weakest.label.toLowerCase()} (${weakest.value.toFixed(1)}/10). Fixing this likely unblocks the most personas.`;
    },
    outcomeBreakdown() {
      const r = this.activeReport();
      if (!r) return { converted: 0, dropped: 0, total: 0, drops: [] };
      const buckets = new Map();
      let converted = 0;
      for (const p of r.personas) {
        if (p.converted) {
          converted += 1;
        } else {
          const key = p.dropped_at || "unknown";
          buckets.set(key, (buckets.get(key) || 0) + 1);
        }
      }
      const drops = Array.from(buckets.entries())
        .map(([stage, count]) => ({ stage, count, label: this.stageLabelInReport(stage, r) }))
        .sort((a, b) => b.count - a.count);
      return {
        converted,
        dropped: r.personas.length - converted,
        total: r.personas.length,
        drops,
      };
    },
    stageLabelInReport(kind, report) {
      if (!kind) return "—";
      if (!report) return STAGE_LABELS[kind] || kind;
      const match = report.stage_aggregates.find((s) => s.stage === kind);
      return match?.label || STAGE_LABELS[kind] || kind;
    },
    funnelCaption() {
      const r = this.activeReport() || this.firstReport();
      if (!r) return "";
      const worst = [...r.stage_aggregates]
        .filter((s) => s.entered > 0 && s.drop_off_rate > 0)
        .sort((a, b) => b.drop_off_rate - a.drop_off_rate)[0];
      if (!worst) return "Every persona continued through every stage.";
      return `Biggest drop at ${worst.label} (${Math.round(worst.drop_off_rate * 100)}% of those who reach it leave here).`;
    },
    abWinnerLabel() {
      const w = this.result?.ab_verdict?.overall_winner;
      if (w === "A") return "Variant A Wins";
      if (w === "B") return "Variant B Wins";
      return "Tie";
    },
    issueContextLine(issue) {
      const r = this.activeReport();
      return `Surfaced on ${this.stageLabelInReport(issue.stage, r)} across ${issue.frequency} persona${issue.frequency === 1 ? "" : "s"}.`;
    },
    scoresLine(s) {
      if (!s) return "";
      return `clarity ${s.clarity} · trust ${s.trust} · price_fit ${s.price_fit} · urgency ${s.urgency} · cta ${s.cta}`;
    },
    reportTimestamp() {
      const d = this.lastRunAt || new Date();
      return "Run at " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    },

    // ================= PERSONAS MODAL =================
    builtInCount() {
      return this.personas.filter((p) => !p.id.startsWith("custom_")).length;
    },
    customCount() {
      return this.personas.filter((p) => p.id.startsWith("custom_")).length;
    },
    filteredPersonas(isCustom) {
      const q = this.personaSearch.trim().toLowerCase();
      return this.personas.filter((p) => {
        if (isCustom !== p.id.startsWith("custom_")) return false;
        if (!q) return true;
        const hay = (p.name + " " + p.archetype + " " + p.character_sheet).toLowerCase();
        return hay.includes(q);
      });
    },
    deletePersonaById(id) {
      const i = this.personas.findIndex((p) => p.id === id);
      if (i >= 0) this.deletePersona(i);
    },

    // ================= STORAGE =================
    SETUPS_KEY: "crowdm.setups",
    RUNS_KEY: "crowdm.runs",
    RUNS_CAP: 30,
    SETUPS_CAP: 30,

    refreshStorage() {
      this.savedSetups = this._readStore(this.SETUPS_KEY);
      this.savedRuns = this._readStore(this.RUNS_KEY);
    },
    _readStore(key) {
      try {
        const raw = localStorage.getItem(key);
        if (!raw) return [];
        const data = JSON.parse(raw);
        return Array.isArray(data) ? data : [];
      } catch (e) {
        return [];
      }
    },
    _writeStore(key, list) {
      try {
        localStorage.setItem(key, JSON.stringify(list));
        return true;
      } catch (e) {
        this.errorMsg = "Browser storage is full. Delete an old saved setup or run first.";
        return false;
      }
    },
    relativeTime(iso) {
      try {
        const d = new Date(iso);
        const diff = (Date.now() - d.getTime()) / 1000;
        if (diff < 60) return "just now";
        if (diff < 3600) return Math.floor(diff / 60) + "m ago";
        if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
        if (diff < 604800) return Math.floor(diff / 86400) + "d ago";
        return d.toLocaleDateString();
      } catch (e) {
        return "";
      }
    },

    _currentSetupPayload() {
      return {
        version: 1,
        campaignA: JSON.parse(JSON.stringify(this.campaignA)),
        campaignB: JSON.parse(JSON.stringify(this.campaignB)),
        abEnabled: this.abEnabled,
        selectedModel: this.selectedModel,
        customOllamaModel: this.customOllamaModel,
        concurrency: this.concurrency,
        personas: this.personas.map((p) => ({
          id: p.id,
          name: p.name,
          archetype: p.archetype,
          icon: p.icon,
          character_sheet: p.character_sheet,
          selected: p.selected,
        })),
      };
    },
    _applySetupPayload(payload) {
      if (!payload) return;
      this.campaignA = payload.campaignA || emptyCampaign("A");
      this.campaignB = payload.campaignB || emptyCampaign("B");
      this.abEnabled = !!payload.abEnabled;
      this.selectedModel = payload.selectedModel || "claude-opus-4-7";
      this.customOllamaModel = payload.customOllamaModel || "";
      this.concurrency = payload.concurrency || 4;
      if (Array.isArray(payload.personas) && payload.personas.length > 0) {
        this.personas = payload.personas.map((p) => ({
          id: p.id,
          name: p.name || "",
          archetype: p.archetype || "",
          icon: p.icon || "👤",
          character_sheet: p.character_sheet || "",
          selected: p.selected !== false,
          editing: false,
        }));
      }
      // make sure stages have uids
      for (const stage of this.campaignA.stages) {
        if (!stage.uid) stage.uid = uid();
      }
    },

    newSetup() {
      if (!confirm("Start a new simulation? Current unsaved setup will be cleared.")) return;
      this.campaignA = emptyCampaign("A");
      this.campaignB = emptyCampaign("B");
      this.abEnabled = false;
      this.errorMsg = "";
      this.result = null;
      this.resetPersonas();
    },

    saveCurrentSetup() {
      const defaultName = this.campaignA.product.name || ("Campaign " + new Date().toLocaleString());
      const name = prompt("Name this setup:", defaultName);
      if (!name) return;
      const now = new Date().toISOString();
      const setup = {
        id: "s_" + Date.now() + "_" + Math.random().toString(36).slice(2, 7),
        name,
        created_at: now,
        updated_at: now,
        payload: this._currentSetupPayload(),
      };
      const list = [setup, ...this.savedSetups].slice(0, this.SETUPS_CAP);
      if (this._writeStore(this.SETUPS_KEY, list)) {
        this.savedSetups = list;
      }
    },
    loadSavedSetup(id) {
      const s = this.savedSetups.find((x) => x.id === id);
      if (!s) return;
      if (!confirm(`Load "${s.name}"? Current setup will be replaced.`)) return;
      this._applySetupPayload(s.payload);
      this.errorMsg = "";
    },
    deleteSavedSetup(id) {
      if (!confirm("Delete this saved setup?")) return;
      const list = this.savedSetups.filter((s) => s.id !== id);
      if (this._writeStore(this.SETUPS_KEY, list)) {
        this.savedSetups = list;
      }
    },

    _saveRunToHistory() {
      if (!this.result) return;
      const now = new Date().toISOString();
      const name = (this.campaignA.product.name || "Run") + " · " + new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      const entry = {
        id: "r_" + Date.now() + "_" + Math.random().toString(36).slice(2, 7),
        name,
        ran_at: now,
        model: this.lastRunModel,
        campaign_name: this.campaignA.product.name || "",
        result: this.result,
      };
      const list = [entry, ...this.savedRuns].slice(0, this.RUNS_CAP);
      if (this._writeStore(this.RUNS_KEY, list)) {
        this.savedRuns = list;
      }
    },
    loadSavedRun(id) {
      const r = this.savedRuns.find((x) => x.id === id);
      if (!r) return;
      this.result = r.result;
      this.lastRunModel = r.model || "";
      this.lastRunAt = new Date(r.ran_at);
      this.activeCampaign = r.result?.reports?.[0]?.campaign_label || "A";
      this.selectedPersonaId = r.result?.reports?.[0]?.personas?.[0]?.persona_id || null;
      this.reportTab = "exec";
      this.view = "report";
    },
    deleteSavedRun(id) {
      if (!confirm("Delete this run from history?")) return;
      const list = this.savedRuns.filter((r) => r.id !== id);
      if (this._writeStore(this.RUNS_KEY, list)) {
        this.savedRuns = list;
      }
    },

    // ================= IMPORT / EXPORT SETUP =================
    exportSetup() {
      const payload = {
        kind: "crowdm.setup",
        version: 1,
        exported_at: new Date().toISOString(),
        name: this.campaignA.product.name || "Crowdm setup",
        setup: this._currentSetupPayload(),
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const slug = (this.campaignA.product.name || "setup").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "setup";
      a.href = url;
      a.download = `crowdm-${slug}-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    },
    async onImportFile(ev) {
      const f = ev.target.files?.[0];
      if (!f) return;
      try {
        const txt = await f.text();
        const data = JSON.parse(txt);
        let payload = null;
        if (data?.kind === "crowdm.setup" && data.setup) {
          payload = data.setup;
        } else if (data?.campaignA) {
          payload = data;
        } else {
          throw new Error("File is not a Crowdm setup export.");
        }
        if (!confirm(`Import setup "${data.name || f.name}"? Current setup will be replaced.`)) {
          ev.target.value = "";
          return;
        }
        this._applySetupPayload(payload);
        this.errorMsg = "";
      } catch (e) {
        this.errorMsg = "Import failed: " + (e?.message || e);
      } finally {
        ev.target.value = "";
      }
    },

    // ================= EXPORT REPORT =================
    exportReport() {
      if (!this.result) return;
      const payload = {
        campaign: this.campaignA.product.name || "campaign",
        ran_at: (this.lastRunAt || new Date()).toISOString(),
        model: this.lastRunModel,
        result: this.result,
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `crowdm-report-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    },
  };
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const s = r.result;
      resolve(typeof s === "string" ? s.split(",")[1] : "");
    };
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}
