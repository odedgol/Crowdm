const STAGE_ORDER = ["ad", "landing_a", "landing_b", "structure", "price", "checkout", "item"];
const STAGE_LABELS = {
  ad: "Native ad",
  landing_a: "Landing page A",
  landing_b: "Landing page B",
  structure: "Structure / offer page",
  price: "Price page",
  checkout: "Checkout",
  item: "Item / product",
};

function emptyCampaign(label) {
  return {
    label,
    product: { name: "", description: "", target_audience: "", price: "", vertical: "e-commerce / physical products" },
    ad: { headline: "", body: "", cta: "", image_base64: null, image_media_type: null },
    stages: STAGE_ORDER.map((kind) => ({
      kind,
      enabled: kind === "ad",
      url: "",
      html: "",
      text: "",
      notes: "",
      screenshot_base64: null,
      screenshot_media_type: null,
    })),
  };
}

function app() {
  return {
    view: "setup",
    health: null,
    personas: [],
    builtInPersonas: [],
    customCounter: 0,
    campaignA: emptyCampaign("A"),
    campaignB: emptyCampaign("B"),
    abEnabled: false,
    running: false,
    progressNote: "",
    errorMsg: "",
    result: null,
    charts: [],

    async init() {
      try {
        const h = await fetch("/api/health").then((r) => r.json());
        this.health = h;
      } catch (e) {}
      try {
        const p = await fetch("/api/personas").then((r) => r.json());
        this.builtInPersonas = p.personas;
        this.resetPersonas();
      } catch (e) {
        this.errorMsg = "Failed to load personas";
      }
      // enable a sensible default set of stages
      for (const s of this.campaignA.stages) {
        if (["ad", "landing_a", "price", "checkout"].includes(s.kind)) s.enabled = true;
      }
      for (const s of this.campaignB.stages) {
        if (["ad", "landing_a", "price", "checkout"].includes(s.kind)) s.enabled = true;
      }
    },

    resetPersonas() {
      this.personas = this.builtInPersonas.map((p, i) => ({
        id: p.id,
        name: p.name,
        archetype: p.archetype,
        character_sheet: p.character_sheet,
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
        selected: true,
        editing: true,
      });
    },

    deletePersona(idx) {
      this.personas.splice(idx, 1);
    },

    selectedCount() {
      return this.personas.filter((p) => p.selected).length;
    },

    stageLabel(kind) {
      return STAGE_LABELS[kind] || kind;
    },

    scoresLine(s) {
      if (!s) return "";
      return `clarity ${s.clarity} · trust ${s.trust} · price_fit ${s.price_fit} · urgency ${s.urgency} · cta ${s.cta}`;
    },

    formatTokens(u) {
      if (!u) return "";
      const fmt = (n) => (n || 0).toLocaleString();
      return `in ${fmt(u.input_tokens)} · out ${fmt(u.output_tokens)} · cache_read ${fmt(u.cache_read_input_tokens)} · cache_create ${fmt(u.cache_creation_input_tokens)}`;
    },

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

    canRun() {
      if (this.selectedCount() === 0) return false;
      const bad = this.personas.find((p) => p.selected && !p.character_sheet.trim());
      if (bad) return false;
      if (!this.campaignA.product.name) return false;
      if (!this.campaignA.ad.headline) return false;
      const hasEnabled = this.campaignA.stages.some((s) => s.enabled);
      return hasEnabled;
    },

    _enabledStages(campaign) {
      return campaign.stages
        .filter((s) => s.enabled)
        .map((s) => ({
          kind: s.kind,
          url: s.url || null,
          html: s.html || null,
          text: s.text || null,
          screenshot_base64: s.screenshot_base64 || null,
          screenshot_media_type: s.screenshot_media_type || null,
          notes: s.notes || null,
        }));
    },

    _prepareCampaignB() {
      const base = JSON.parse(JSON.stringify(this.campaignA));
      const b = this.campaignB;
      base.label = "B";
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
      this.progressNote = "calling Claude for each persona × stage (this can take 30–90s)";
      try {
        const a = JSON.parse(JSON.stringify(this.campaignA));
        a.label = "A";
        a.stages = this._enabledStages(this.campaignA);
        const campaigns = [a];
        if (this.abEnabled) {
          const b = this._prepareCampaignB();
          b.stages = this._enabledStages({ stages: b.stages });
          campaigns.push(b);
        }
        const payload = {
          campaigns,
          personas: this.personas
            .filter((p) => p.selected)
            .map((p) => ({
              id: p.id,
              name: p.name,
              archetype: p.archetype,
              character_sheet: p.character_sheet,
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
        this.view = "report";
        await this.$nextTick();
        this._renderCharts();
      } catch (e) {
        this.errorMsg = e.message || String(e);
      } finally {
        this.running = false;
      }
    },

    _renderCharts() {
      for (const ch of this.charts) ch.destroy();
      this.charts = [];
      (this.result?.reports || []).forEach((report, idx) => {
        const el = document.getElementById("funnel-" + idx);
        if (!el) return;
        const labels = report.stage_aggregates.map((s) => s.label);
        const entered = report.stage_aggregates.map((s) => s.entered);
        const continued = report.stage_aggregates.map((s) => s.continued);
        const ctx = el.getContext("2d");
        const chart = new Chart(ctx, {
          type: "bar",
          data: {
            labels,
            datasets: [
              { label: "Entered stage", data: entered, backgroundColor: "rgba(59,130,246,0.6)" },
              { label: "Continued", data: continued, backgroundColor: "rgba(34,197,94,0.7)" },
            ],
          },
          options: {
            responsive: true,
            scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
          },
        });
        this.charts.push(chart);
      });
    },

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
          image_base64: null,
          image_media_type: null,
        },
        stages: STAGE_ORDER.map((kind) => ({
          kind,
          enabled: ["ad", "landing_a", "structure", "price", "checkout"].includes(kind),
          url: "",
          html: "",
          text:
            kind === "landing_a"
              ? "Headline: Finally, a morning that doesn't feel like a punishment. Body: AuroraGlow mimics the real sunrise over 30 minutes, gently raising melatonin-suppressing light levels so your body wakes naturally. 4.8★ from 2,400 reviews. See it in action. [Watch 90-sec demo button]"
              : kind === "structure"
              ? "What's in the box: AuroraGlow unit, USB-C cable, magnetic base, setup card. Specs: 20 light modes, Bluetooth 5.3 speaker, FM radio, 7-day programmable alarms, touch + app control. Warranty: 2 years. Ships in 2-3 days."
              : kind === "price"
              ? "AuroraGlow LED Sunrise Alarm — $79 (was $119, save $40). Subscribe to the newsletter and save another $10 on your next order. Free US shipping. Sleep Bundle: add the pillow mist for $19 more."
              : kind === "checkout"
              ? "Cart: AuroraGlow × 1 — $79. Shipping: Free. Tax: calculated at next step. Total: $79. Enter email, shipping address, payment. Guest checkout available. Apple Pay / Google Pay / PayPal."
              : "",
          notes: "",
          screenshot_base64: null,
          screenshot_media_type: null,
        })),
      };
    },
  };
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const s = r.result;
      const b64 = typeof s === "string" ? s.split(",")[1] : "";
      resolve(b64);
    };
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}
