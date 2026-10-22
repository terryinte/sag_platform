const TITLES = {
  clients: "客户 / 项目",
  wizard: "新建项目向导",
  config: "项目配置",
  runs: "采集任务",
  dashboard: "可见度总览",
  sources: "引用来源",
  answer: "回答详情",
  assessment: "评分与建议",
  plan: "30 天改进计划",
  report: "报告预览",
  playbooks: "整改建议库",
  playbook: "建议详情",
  collection: "采集方案",
  architecture: "技术架构",
  channels: "采集通道",
  keywords: "添加测试关键词",
};
const GLOBAL = new Set(["clients", "wizard", "playbooks", "collection", "architecture", "channels"]);
const ENGINES = ["ChatGPT", "Perplexity", "Gemini", "Claude", "DeepSeek", "Kimi", "文心", "OpenRouter", "ChatGPT 网页", "Google AI 概览", "Copilot"];
const state = {
  tabs: [],
  active: null,
  projectId: null,
  projects: [],
  wizard: { step: 0, project: null, questions: [], questionSetId: null, contents: [] },
};

const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));

function toast(message) {
  const el = document.querySelector("#toast");
  el.textContent = message;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2400);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let body = {};
    try { body = await response.json(); } catch { /* ignore */ }
    const detail = body.detail;
    throw new Error(typeof detail === "string" ? detail : `请求失败 ${response.status}`);
  }
  const type = response.headers.get("content-type") || "";
  return type.includes("json") ? response.json() : response.text();
}

function projectName(projectId) {
  const project = state.projects.find((item) => item.id === projectId);
  return project ? project.brand_name || project.name : "";
}

function syncSelect() {
  const select = document.querySelector("#project-select");
  select.innerHTML = state.projects.length
    ? state.projects.map((item) => `<option value="${item.id}" ${item.id === state.projectId ? "selected" : ""}>${esc(item.brand_name)} · ${esc(item.name)}</option>`).join("")
    : `<option value="">尚未创建项目</option>`;
}

async function refreshProjects() {
  state.projects = await api("/api/projects");
  if (!state.projectId && state.projects[0]) state.projectId = state.projects[0].id;
  if (state.projectId && !state.projects.some((item) => item.id === state.projectId)) {
    state.projectId = state.projects[0] ? state.projects[0].id : null;
  }
  syncSelect();
}

function tabKey(page, projectId, extra) {
  extra = extra || {};
  if (page === "playbook") return `playbook:${Number(extra.id) || extra.id || ""}`;
  if (GLOBAL.has(page)) return page;
  const id = Number(projectId);
  return `${page}:${Number.isFinite(id) ? id : projectId}`;
}

function openTab(page, projectId, title, extra, navId) {
  extra = extra || {};
  const scopedId = projectId || state.projectId;
  if (!GLOBAL.has(page) && page !== "playbook" && !scopedId) {
    toast("请先在客户列表选择项目");
    if (page !== "clients") openTab("clients");
    return;
  }
  const key = tabKey(page, scopedId, extra);
  const nav = navId || (page === "playbook" ? "playbooks" : page);
  const existing = state.tabs.find((tab) => tab.key === key);
  if (existing) {
    if (navId) existing.nav = nav;
    existing.extra = existing.extra || {};
    if (page === "answer") {
      existing.extra.attemptId = extra.attemptId || null;
      existing.title = extra.attemptId
        ? (title || existing.title)
        : `${TITLES.answer} · ${projectName(existing.projectId)}`;
    } else if (extra.id) {
      existing.extra.id = extra.id;
    }
    state.active = existing.key;
    renderTabs();
    renderActive();
    return;
  }
  const tabTitle = title || (GLOBAL.has(page) || page === "playbook" ? TITLES[page] : `${TITLES[page]} · ${projectName(scopedId)}`);
  state.tabs.push({
    key,
    page,
    nav,
    projectId: GLOBAL.has(page) ? null : Number(scopedId) || scopedId,
    title: tabTitle,
    extra: { ...extra },
  });
  state.active = key;
  renderTabs();
  renderActive();
}

function closeTab(key, event) {
  event.stopPropagation();
  const index = state.tabs.findIndex((tab) => tab.key === key);
  if (index < 0) return;
  state.tabs.splice(index, 1);
  if (state.active === key) {
    const next = state.tabs[Math.min(index, state.tabs.length - 1)];
    state.active = next ? next.key : null;
  }
  renderTabs();
  renderActive();
}

function renderTabs() {
  const active = state.tabs.find((tab) => tab.key === state.active);
  document.querySelectorAll(".navbtn[data-nav]").forEach((button) => {
    button.classList.toggle("on", !!active && button.dataset.nav === (active.nav || active.page));
  });
  document.querySelector("#crumb").textContent = active ? active.title : "客户 / 项目";
  document.querySelector("#tabs").innerHTML = state.tabs.map((tab) => (
    `<button class="tab ${tab.key === state.active ? "on" : ""}" type="button" data-key="${esc(tab.key)}">${esc(tab.title)} <span class="x" data-close="${esc(tab.key)}">×</span></button>`
  )).join("");
  document.querySelectorAll("#tabs .tab").forEach((button) => {
    button.onclick = () => {
      state.active = button.dataset.key;
      renderTabs();
      renderActive();
    };
  });
  document.querySelectorAll("#tabs .x").forEach((button) => {
    button.onclick = (event) => closeTab(button.dataset.close, event);
  });
}

async function renderActive() {
  const tab = state.tabs.find((item) => item.key === state.active);
  const panel = document.querySelector("#panel");
  if (!tab) {
    panel.innerHTML = `<div class="card"><p>标签已全部关闭。</p><button class="btn pri" type="button" id="reopen">打开客户列表</button></div>`;
    document.querySelector("#reopen").onclick = () => openTab("clients");
    return;
  }
  if (tab.page !== "wizard") panel.innerHTML = `<p class="sub">加载中…</p>`;
  try {
    await RENDER[tab.page](tab, panel);
  } catch (error) {
    panel.innerHTML = `<div class="card">${esc(error.message)}</div>`;
  }
}

function rate(value) {
  return value == null ? "—" : `${value}%`;
}

async function renderClients(_tab, panel) {
  const data = await api("/api/geo/portfolio");
  const k = data.kpis;
  const rows = data.projects.map((item) => `
    <tr>
      <td><b>${esc(item.client_name)}</b><br><span style="color:#64748b">${esc(item.brand_name)}</span></td>
      <td>${esc(item.industry || "—")}</td>
      <td><span class="tag">${esc(item.delivery_status)}</span></td>
      <td>${esc(item.delivery_stage)}</td>
      <td><b>${rate(item.mention_rate)}</b></td>
      <td>${esc(item.next_run_at || "—")}</td>
      <td>
        <button class="btn sm" type="button" data-open="dashboard" data-id="${item.project_id}" data-title="看板 · ${esc(item.brand_name)}">看板</button>
        <button class="btn sm" type="button" data-open="config" data-id="${item.project_id}">配置</button>
        <button class="btn sm" type="button" data-open="runs" data-id="${item.project_id}">采集</button>
        <button class="btn sm" type="button" data-open="report" data-id="${item.project_id}">报告</button>
      </td>
    </tr>`).join("");
  panel.innerHTML = `
    <h1>客户与项目</h1>
    <p class="sub">按「诊断报告 → 30 天改进 → 月度监测」管理。点某一行的看板，只打开该项目的可见度。</p>
    <div class="grid g4" style="margin-bottom:16px">
      <div class="card kpi"><div class="l">在服务客户</div><div class="v">${k.clients}</div></div>
      <div class="card kpi"><div class="l">项目数</div><div class="v">${k.projects}</div></div>
      <div class="card kpi"><div class="l">本月采集调用</div><div class="v">${k.attempts_this_month}</div></div>
      <div class="card kpi"><div class="l">待复核 / 本月费用</div><div class="v">${k.pending_reviews}</div><span class="l">估算 $${k.spend_usd}</span></div>
    </div>
    <div class="card"><h3>项目列表</h3>
      <table><tr><th>客户</th><th>行业</th><th>状态</th><th>服务阶段</th><th>K 类提及率</th><th>下次采集</th><th></th></tr>
      ${rows || `<tr><td colspan="7">还没有项目。使用新建项目向导开始。</td></tr>`}
      </table>
    </div>`;
  panel.querySelectorAll("[data-open]").forEach((button) => {
    button.onclick = () => {
      const projectId = Number(button.dataset.id);
      state.projectId = projectId;
      syncSelect();
      openTab(button.dataset.open, projectId, button.dataset.title || undefined);
    };
  });
}

function wizardForm() {
  return state.wizard;
}

async function renderWizard(_tab, panel) {
  const wizard = wizardForm();
  const labels = ["① 录入客户", "② 关键内容", "③ 生成问题库", "④ 启动监测", "⑤ 调整与版本", "⑥ 完成"];
  const steps = labels.map((label, index) => `<div class="${index === wizard.step ? "on" : index < wizard.step ? "done" : ""}">${label}</div>`).join("");
  let body = "";
  if (wizard.step === 0) {
    body = `<div class="grid g2"><div><label>客户名称</label><input id="w-client" value="${esc(wizard.client_name || "")}"><label>品牌名</label><input id="w-brand" value="${esc(wizard.brand_name || "")}"><label>项目名称</label><input id="w-project" value="${esc(wizard.project_name || "")}" placeholder="例如：美国站 GEO 监测"><label>别名（逗号分隔）</label><input id="w-aliases" value="${esc(wizard.aliases || "")}"><label>官网</label><input id="w-domain" value="${esc(wizard.domain || "")}"></div><div><label>行业</label><input id="w-industry" value="${esc(wizard.industry || "")}"><label>语言</label><select id="w-lang"><option value="zh-CN">中文 zh-CN</option><option value="en-US">英语 en-US</option></select><label>市场</label><input id="w-region" value="${esc(wizard.region || "中国大陆")}"><label>竞品（逗号分隔，可用 名称|域名）</label><input id="w-competitors" value="${esc(wizard.competitors || "")}"></div></div>`;
  } else if (wizard.step === 1) {
    const cards = (wizard.contents.length ? wizard.contents : [{ kind: "产品线", title: "", body: "" }]).map((item, index) => `
      <div class="card"><label>类型</label><select data-kind="${index}"><option ${item.kind === "产品线" ? "selected" : ""}>产品线</option><option ${item.kind === "卖点" ? "selected" : ""}>卖点</option><option ${item.kind === "参数" ? "selected" : ""}>参数</option></select><label>标题</label><input data-title="${index}" value="${esc(item.title)}"><label>说明</label><textarea data-body="${index}" rows="2">${esc(item.body || "")}</textarea></div>`).join("");
    body = `<p class="sub">官网自动抓取还没接。请手工填写产品、卖点和参数，这些内容会用来生成 D/K 问题。</p><div class="grid g3" id="content-grid">${cards}</div><p><button class="btn sm" type="button" id="add-content">添加一条</button></p>`;
  } else if (wizard.step === 2) {
    const rows = (wizard.questions || []).map((item) => `
      <tr><td><span class="tag ${item.probe_type === "K" ? "t-pri" : "t-warn"}">${esc(item.probe_type)}</span></td><td>${esc(item.intent)}</td><td><input data-qid="${item.id}" value="${esc(item.question)}"></td><td style="color:#64748b">${esc(item.rationale || "")}</td></tr>`).join("");
    body = `<p><span class="tag t-pri">共 ${wizard.questions.length} 题</span> <button class="btn sm" type="button" id="regen">重新生成</button> <button class="btn sm pri" type="button" id="save-qs">保存修改</button></p><table><tr><th>类型</th><th>意图</th><th>问题（可编辑）</th><th>依据</th></tr>${rows || "<tr><td colspan='4'>还没有问题</td></tr>"}</table>`;
  } else if (wizard.step === 3) {
    body = await strategyBody(wizard);
  } else if (wizard.step === 4) {
    body = `<ul><li>修改问题、引擎或采样次数会生成新的问题库版本和新的 config_hash，旧采集保留。</li><li>看板只把哈希相同的两期放在一起比较，不同则标明口径变化。</li><li>D 类问题不能用来计算自然发现率。</li></ul>`;
  } else {
    body = `<p>项目已创建。第一期采集任务已经落库。</p><button class="btn pri" type="button" id="goto-board">进入该项目看板</button> <button class="btn" type="button" id="goto-runs">查看采集批次</button>`;
  }
  panel.innerHTML = `<h1>新建项目向导</h1><p class="sub">录入客户 → 关键内容 → 自动生成问题库 → 开始监测 → 调整 → 出报告</p><div class="steps">${steps}</div><div class="card">${body}<div style="margin-top:16px;display:flex;justify-content:space-between"><button class="btn" type="button" id="prev" ${wizard.step === 0 ? "disabled" : ""}>上一步</button><button class="btn pri" type="button" id="next">${wizard.step === 5 ? "完成" : "下一步"}</button></div></div>`;
  const lang = panel.querySelector("#w-lang");
  if (lang && wizard.language) lang.value = wizard.language;
  panel.querySelector("#prev").onclick = () => { wizard.step = Math.max(0, wizard.step - 1); renderWizard(_tab, panel); };
  panel.querySelector("#next").onclick = () => advanceWizard(panel);
  const add = panel.querySelector("#add-content");
  if (add) add.onclick = () => { readContents(panel, true); wizard.contents.push({ kind: "卖点", title: "", body: "" }); renderWizard(_tab, panel); };
  const regen = panel.querySelector("#regen");
  if (regen) regen.onclick = () => generateWizard(true);
  const save = panel.querySelector("#save-qs");
  if (save) save.onclick = () => saveQuestions(panel);
  bindStrategy(panel, wizard.project && wizard.project.id);
  const board = panel.querySelector("#goto-board");
  if (board && wizard.project) board.onclick = () => openTab("dashboard", wizard.project.id, `看板 · ${wizard.project.brand_name}`);
  const runs = panel.querySelector("#goto-runs");
  if (runs && wizard.project) runs.onclick = () => openTab("runs", wizard.project.id);
}

function readStep0(panel) {
  const wizard = state.wizard;
  wizard.client_name = panel.querySelector("#w-client").value.trim();
  wizard.brand_name = panel.querySelector("#w-brand").value.trim();
  wizard.project_name = panel.querySelector("#w-project").value.trim();
  wizard.aliases = panel.querySelector("#w-aliases").value.trim();
  wizard.domain = panel.querySelector("#w-domain").value.trim();
  wizard.industry = panel.querySelector("#w-industry").value.trim();
  wizard.language = panel.querySelector("#w-lang").value;
  wizard.region = panel.querySelector("#w-region").value.trim();
  wizard.competitors = panel.querySelector("#w-competitors").value.trim();
}

function readContents(panel, keepEmpty) {
  const wizard = state.wizard;
  const items = [...panel.querySelectorAll("[data-title]")].map((input) => ({
    kind: panel.querySelector(`[data-kind="${input.dataset.title}"]`).value,
    title: input.value.trim(),
    body: panel.querySelector(`[data-body="${input.dataset.title}"]`).value.trim(),
    confirmed: true,
  }));
  wizard.contents = keepEmpty ? items : items.filter((item) => item.title);
}

function selectedEngines(panel) {
  return [...panel.querySelectorAll("#engine-chips span.on")].map((item) => item.dataset.engine);
}

function budgetLine(estimate) {
  if (!estimate) return "正在估算费用…";
  const cap = estimate.over_cap ? " 预计费用超过某个通道的单次预算上限。" : "";
  return `预计本次约 $${estimate.estimated_cost_usd}（${estimate.api_calls} 次 API）。已花费 $${estimate.spent_usd}。${estimate.note || ""}${cap}`;
}

async function strategyBody(wizard) {
  const defaults = ["ChatGPT", "Perplexity", "Gemini", "DeepSeek"];
  let channels = [];
  let strategy = { channels: [], sample_count: 1, cadence: "monthly", web_sample_percent: 15 };
  let estimate = null;
  if (wizard.project) {
    channels = await api("/api/geo/channels");
    strategy = await api(`/api/projects/${wizard.project.id}/collection-strategy`);
  }
  const selected = new Set(wizard.engines || strategy.channels || []);
  if (!wizard.engines && !strategy.channels.length) defaults.forEach((item) => selected.add(item));
  wizard.engines = [...selected];
  const sampleCount = wizard.sampleCount || strategy.sample_count || 1;
  const cadence = wizard.cadenceChoice || strategy.cadence || "monthly";
  const webPercent = wizard.webPercent == null ? (strategy.web_sample_percent ?? 15) : wizard.webPercent;
  if (wizard.project) {
    estimate = await api(`/api/projects/${wizard.project.id}/geo/budget-estimate`, {
      method: "POST",
      body: JSON.stringify({ engines: wizard.engines, sample_count: Number(sampleCount) || 1 }),
    });
  }
  const chips = channels.map((item) => {
    const mark = item.kind === "web" ? " · P1/未实现" : "";
    const on = selected.has(item.engine) ? "on" : "";
    return `<span class="${on}" data-engine="${esc(item.engine)}">${esc(item.label)}${mark}</span>`;
  }).join("");
  return `<label>采集通道（网页类是 P1，只记录计划抽样）</label><div class="chips" id="engine-chips">${chips}</div>
    <div class="grid g3"><div><label>每题采样次数</label><select id="samples"><option value="1" ${Number(sampleCount) === 1 ? "selected" : ""}>1 次</option><option value="3" ${Number(sampleCount) === 3 ? "selected" : ""}>3 次</option></select></div>
    <div><label>频率</label><select id="cadence"><option value="monthly" ${cadence === "monthly" ? "selected" : ""}>每月一次</option><option value="weekly" ${cadence === "weekly" ? "selected" : ""}>每周一次</option></select></div>
    <div><label>网页抽样核对（核心问题）</label><input id="web-percent" type="number" min="0" max="100" value="${esc(webPercent)}"> <span class="sub">默认 15%</span></div></div>
    <label>月度预算（美元，可空）</label><input id="budget" placeholder="60" value="${esc(wizard.monthlyBudget || "")}">
    <p id="est">${esc(budgetLine(estimate))}</p>
    <p class="sub">没有密钥的官方 API 会记为模拟并跳过真实请求。浏览器通道不会打开网页，只按比例记下计划抽样。</p>`;
}

function bindStrategy(panel, projectId) {
  const chips = panel.querySelector("#engine-chips");
  if (!chips) return;
  const refresh = async () => {
    if (!projectId) return;
    const engines = selectedEngines(panel);
    const sample = Number(panel.querySelector("#samples").value) || 1;
    try {
      const estimate = await api(`/api/projects/${projectId}/geo/budget-estimate`, {
        method: "POST",
        body: JSON.stringify({ engines, sample_count: sample }),
      });
      const line = panel.querySelector("#est");
      if (line) line.textContent = budgetLine(estimate);
    } catch (error) {
      toast(error.message);
    }
  };
  chips.querySelectorAll("span").forEach((chip) => {
    chip.onclick = () => { chip.classList.toggle("on"); refresh(); };
  });
  const samples = panel.querySelector("#samples");
  if (samples) samples.onchange = refresh;
}

async function advanceWizard(panel) {
  const wizard = state.wizard;
  try {
    if (wizard.step === 0) {
      readStep0(panel);
      if (!wizard.client_name || !wizard.brand_name || !wizard.domain) throw new Error("请填写客户、品牌和官网");
      if (!wizard.contents.length) {
        wizard.contents = [
          { kind: "产品线", title: "", body: "" },
          { kind: "卖点", title: "", body: "" },
        ];
      }
    } else if (wizard.step === 1) {
      readContents(panel, true);
      const filled = wizard.contents.filter((item) => item.title);
      if (!filled.length) throw new Error("至少填写一条产品或卖点");
      if (!wizard.project) {
        wizard.project = await api("/api/geo/bootstrap", {
          method: "POST",
          body: JSON.stringify({
            client_name: wizard.client_name,
            brand_name: wizard.brand_name,
            domain: wizard.domain,
            industry: wizard.industry || "",
            aliases: wizard.aliases || "",
            competitors: wizard.competitors.split(/[,，]/).map((item) => item.trim()).filter(Boolean),
            language: wizard.language || "zh-CN",
            region: wizard.region || "中国大陆",
            key_contents: filled,
            project_name: wizard.project_name || `${wizard.brand_name} GEO 监测`,
          }),
        });
        state.projectId = wizard.project.id;
        await refreshProjects();
      }
      await generateWizard(false);
      return;
    } else if (wizard.step === 2) {
      await saveQuestions(panel);
    } else if (wizard.step === 3) {
      const engines = selectedEngines(panel);
      if (!engines.length) throw new Error("至少选择一个引擎");
      const sampleCount = Number(panel.querySelector("#samples").value);
      const webPercent = Number(panel.querySelector("#web-percent").value);
      const cadence = panel.querySelector("#cadence").value;
      if (!Number.isFinite(webPercent) || webPercent < 0 || webPercent > 100) throw new Error("网页抽样比例需在 0 到 100 之间");
      wizard.engines = engines;
      wizard.sampleCount = sampleCount;
      wizard.webPercent = webPercent;
      wizard.cadenceChoice = cadence;
      wizard.monthlyBudget = panel.querySelector("#budget").value.trim();
      await api(`/api/projects/${wizard.project.id}/collection-strategy`, {
        method: "PUT",
        body: JSON.stringify({ channels: engines, sample_count: sampleCount, cadence, web_sample_percent: webPercent }),
      });
      const baseline = await api(`/api/projects/${wizard.project.id}/geo/baselines`, {
        method: "POST",
        body: JSON.stringify({
          question_set_id: wizard.questionSetId,
          engines,
          language: wizard.language || "zh-CN",
          region: wizard.region || "中国大陆",
          sample_count: sampleCount,
          web_sample_percent: webPercent,
        }),
      });
      const budget = wizard.monthlyBudget;
      await api(`/api/projects/${wizard.project.id}/profile`, {
        method: "PUT",
        body: JSON.stringify({ cadence, monthly_budget_usd: budget ? Number(budget) : null, delivery_status: "诊断中" }),
      });
      wizard.monitor = await api(`/api/projects/${wizard.project.id}/geo/monitor`, {
        method: "POST",
        body: JSON.stringify({ baseline_id: baseline.id }),
      });
      toast(`采集结束：${wizard.monitor.status}`);
    }
    wizard.step = Math.min(5, wizard.step + 1);
    renderWizard(null, panel);
  } catch (error) {
    toast(error.message);
  }
}

async function generateWizard(force) {
  const wizard = state.wizard;
  if (!force && wizard.questions.length) {
    wizard.step = 2;
    renderActive();
    return;
  }
  const generated = await api(`/api/projects/${wizard.project.id}/geo/questions/generate`, {
    method: "POST",
    body: JSON.stringify({ name: "自动问题库", llm: true }),
  });
  wizard.questionSetId = generated.question_set.id;
  wizard.questions = generated.questions;
  wizard.step = 2;
  toast(generated.source === "llm" ? "已用模型生成问题" : "未配置模型密钥，已用本地模板生成，可直接改");
  renderActive();
}

async function saveQuestions(panel) {
  const wizard = state.wizard;
  const inputs = [...panel.querySelectorAll("[data-qid]")];
  for (const input of inputs) {
    const current = wizard.questions.find((item) => String(item.id) === input.dataset.qid);
    if (!current || input.value.trim() === current.question) continue;
    const updated = await api(`/api/geo/questions/${current.id}`, {
      method: "PUT",
      body: JSON.stringify({
        intent: current.intent,
        question: input.value.trim(),
        weight: current.weight,
        expected_facts: current.expected_facts || "",
        probe_type: current.probe_type,
        language: current.language || "zh-CN",
        rationale: current.rationale || "",
      }),
    });
    Object.assign(current, updated);
  }
}

async function renderConfig(tab, panel) {
  const project = await api(`/api/projects/${tab.projectId}`);
  const contents = await api(`/api/projects/${tab.projectId}/key-contents`);
  const sets = await api(`/api/projects/${tab.projectId}/geo/question-sets`);
  const questions = sets[0] ? await api(`/api/geo/question-sets/${sets[0].id}/questions`) : [];
  const baselines = await api(`/api/projects/${tab.projectId}/geo/baselines`);
  const channels = await api("/api/geo/channels");
  const strategy = await api(`/api/projects/${tab.projectId}/collection-strategy`);
  const chosen = new Set(strategy.channels.length ? strategy.channels : ["ChatGPT", "Perplexity", "Gemini", "DeepSeek"]);
  const estimate = await api(`/api/projects/${tab.projectId}/geo/budget-estimate`, {
    method: "POST",
    body: JSON.stringify({ engines: [...chosen], sample_count: strategy.sample_count || 1, question_set_id: sets[0] ? sets[0].id : null }),
  });
  const chips = channels.map((item) => `<span class="${chosen.has(item.engine) ? "on" : ""}" data-engine="${esc(item.engine)}">${esc(item.label)}${item.kind === "web" ? " · P1/未实现" : ""}</span>`).join("");
  panel.innerHTML = `
    <h1>项目配置 · ${esc(project.brand_name)}</h1>
    <p class="sub">保存快照会冻结引擎、语言、市场、采样次数和问题文本，并计算 config_hash。</p>
    <div class="grid g2">
      <div class="card"><h3>品牌与竞品</h3>
        <label>别名</label><input id="aliases" value="${esc(project.aliases || "")}">
        <label>阶段</label><select id="stage">${["诊断报告", "30 天计划", "月度监测"].map((item) => `<option ${project.delivery_stage === item ? "selected" : ""}>${item}</option>`).join("")}</select>
        <label>状态</label><select id="status">${["试用", "诊断中", "改进期", "监测中"].map((item) => `<option ${project.delivery_status === item ? "selected" : ""}>${item}</option>`).join("")}</select>
        <p><button class="btn sm pri" type="button" id="save-profile">保存资料</button></p>
        <p>竞品：${project.competitors.map((item) => esc(item.name)).join("、") || "无"}</p>
      </div>
      <div class="card"><h3>关键内容</h3>${contents.map((item) => `<p><span class="tag">${esc(item.kind)}</span> ${esc(item.title)}</p>`).join("") || "<p>还没有关键内容</p>"}
        <label>新增类型</label><select id="ckind"><option>产品线</option><option>卖点</option><option>参数</option></select>
        <label>标题</label><input id="ctitle"><button class="btn sm" type="button" id="add-kc">添加</button>
      </div>
    </div>
    <div class="card" style="margin-top:16px"><h3>问题库 ${sets[0] ? esc(sets[0].version) : ""} <small>D 类不能拿来算自然发现率</small></h3>
      <table><tr><th>类型</th><th>意图</th><th>问题</th></tr>${questions.map((item) => `<tr><td><span class="tag ${item.probe_type === "D" ? "t-warn" : "t-pri"}">${esc(item.probe_type || "K")}</span></td><td>${esc(item.intent)}</td><td>${esc(item.question)}</td></tr>`).join("") || "<tr><td colspan='3'>请先在向导中生成问题</td></tr>"}</table>
      <h3 style="margin-top:16px">采集策略</h3>
      <div class="chips" id="cfg-engines">${chips}</div>
      <div class="grid g3"><div><label>每题采样次数</label><select id="cfg-samples"><option value="1" ${strategy.sample_count === 1 ? "selected" : ""}>1 次</option><option value="3" ${strategy.sample_count === 3 ? "selected" : ""}>3 次</option></select></div>
      <div><label>频率</label><select id="cfg-cadence"><option value="monthly" ${strategy.cadence === "monthly" ? "selected" : ""}>每月一次</option><option value="weekly" ${strategy.cadence === "weekly" ? "selected" : ""}>每周一次</option></select></div>
      <div><label>网页抽样核对 %</label><input id="cfg-web" type="number" min="0" max="100" value="${esc(strategy.web_sample_percent ?? 15)}"></div></div>
      <p id="cfg-est">${esc(budgetLine(estimate))}</p>
      <p><button class="btn pri" type="button" id="snapshot" ${sets[0] ? "" : "disabled"}>保存快照并开始采集</button></p>
      <p class="sub">已有快照：${baselines.map((item) => esc(item.config_hash.slice(0, 8))).join("、") || "无"}</p>
    </div>`;
  const refreshConfigEstimate = async () => {
    const engines = [...panel.querySelectorAll("#cfg-engines span.on")].map((item) => item.dataset.engine);
    const est = await api(`/api/projects/${tab.projectId}/geo/budget-estimate`, {
      method: "POST",
      body: JSON.stringify({ engines, sample_count: Number(panel.querySelector("#cfg-samples").value) || 1, question_set_id: sets[0] ? sets[0].id : null }),
    });
    panel.querySelector("#cfg-est").textContent = budgetLine(est);
  };
  panel.querySelectorAll("#cfg-engines span").forEach((chip) => { chip.onclick = () => { chip.classList.toggle("on"); refreshConfigEstimate(); }; });
  panel.querySelector("#cfg-samples").onchange = refreshConfigEstimate;
  panel.querySelector("#save-profile").onclick = async () => {
    await api(`/api/projects/${tab.projectId}/profile`, { method: "PUT", body: JSON.stringify({ aliases: panel.querySelector("#aliases").value, delivery_stage: panel.querySelector("#stage").value, delivery_status: panel.querySelector("#status").value }) });
    toast("已保存");
  };
  panel.querySelector("#add-kc").onclick = async () => {
    await api(`/api/projects/${tab.projectId}/key-contents`, { method: "POST", body: JSON.stringify({ kind: panel.querySelector("#ckind").value, title: panel.querySelector("#ctitle").value, confirmed: true }) });
    renderActive();
  };
  const snapshot = panel.querySelector("#snapshot");
  if (snapshot) snapshot.onclick = async () => {
    const engines = [...panel.querySelectorAll("#cfg-engines span.on")].map((item) => item.dataset.engine);
    const sampleCount = Number(panel.querySelector("#cfg-samples").value) || 1;
    const webPercent = Number(panel.querySelector("#cfg-web").value);
    const cadence = panel.querySelector("#cfg-cadence").value;
    await api(`/api/projects/${tab.projectId}/collection-strategy`, { method: "PUT", body: JSON.stringify({ channels: engines, sample_count: sampleCount, cadence, web_sample_percent: webPercent }) });
    const baseline = await api(`/api/projects/${tab.projectId}/geo/baselines`, { method: "POST", body: JSON.stringify({ question_set_id: sets[0].id, engines, language: project.language || "zh-CN", region: project.region || "中国大陆", sample_count: sampleCount, web_sample_percent: webPercent }) });
    const result = await api(`/api/projects/${tab.projectId}/geo/monitor`, { method: "POST", body: JSON.stringify({ baseline_id: baseline.id }) });
    toast(`采集 ${result.status}`);
    openTab("runs", tab.projectId);
  };
}

async function renderRuns(tab, panel) {
  const runs = await api(`/api/projects/${tab.projectId}/geo/runs`);
  const attempts = await api(`/api/projects/${tab.projectId}/geo/attempts`);
  const grouped = {};
  attempts.forEach((item) => {
    const bucket = grouped[item.engine] || { engine: item.engine, access: item.access, total: 0, ok: 0, skipped: 0 };
    bucket.total += 1;
    if (item.status === "ok") bucket.ok += 1;
    else bucket.skipped += 1;
    grouped[item.engine] = bucket;
  });
  panel.innerHTML = `
    <h1>采集任务 · ${esc(projectName(tab.projectId))}</h1>
    <p class="sub">每次请求先落一条 attempt（含配置哈希和原文摘要），再派生引用和判定。浏览器通道是 stub。</p>
    <div class="card"><h3>最近批次</h3><table><tr><th>日期</th><th>状态</th><th>问题库</th><th>回答/复核</th></tr>${runs.map((item) => `<tr><td>${esc(item.run_at)}</td><td>${esc(item.status)}</td><td>${esc(item.question_set_name)} ${esc(item.version)}</td><td>${item.response_count}/${item.reviewed_count || 0}</td></tr>`).join("") || "<tr><td colspan='4'>还没有批次</td></tr>"}</table></div>
    <div class="card" style="margin-top:16px"><h3>通道</h3><table><tr><th>引擎</th><th>方式</th><th>计划</th><th>成功</th><th>跳过/失败</th></tr>${Object.values(grouped).map((item) => `<tr><td>${esc(item.engine)}</td><td><span class="tag">${esc(item.access)}</span></td><td>${item.total}</td><td>${item.ok}</td><td>${item.skipped}</td></tr>`).join("") || "<tr><td colspan='5'>还没有尝试</td></tr>"}</table></div>
    <div class="card" style="margin-top:16px"><h3>尝试明细</h3><table><tr><th>问题</th><th>引擎</th><th>状态</th><th></th></tr>${attempts.slice(0, 40).map((item) => `<tr><td>${esc(item.question)}</td><td>${esc(item.engine)}</td><td><span class="tag ${item.status === "ok" ? "t-ok" : "t-warn"}">${esc(item.status)} ${esc(item.error_code || "")}</span></td><td><button class="btn sm" type="button" data-attempt="${item.id}">查看</button></td></tr>`).join("")}</table></div>`;
  panel.querySelectorAll("[data-attempt]").forEach((button) => {
    button.onclick = () => openTab("answer", tab.projectId, `回答 ${button.dataset.attempt}`, { attemptId: Number(button.dataset.attempt) });
  });
}

async function renderDashboard(tab, panel) {
  const vis = await api(`/api/projects/${tab.projectId}/geo/visibility`);
  const engines = vis.engines || [];
  const matrix = (vis.matrix || []).map((row) => `<tr><td><span class="tag ${row.probe_type === "D" ? "t-warn" : "t-pri"}">${esc(row.probe_type)}</span> ${esc(row.question)}</td>${engines.map((engine) => { const cell = (row.cells || {})[engine]; const text = cell ? cell.text : "—"; const tone = !cell || !cell.valid ? "#f8fafc" : cell.mentioned === cell.valid ? "#86efac" : cell.mentioned ? "#fef3c7" : "#fee2e2"; return `<td class="c" style="background:${tone}">${esc(text)}</td>`; }).join("")}</tr>`).join("");
  const share = (vis.share || []).map((item) => `<div style="display:flex;gap:8px;align-items:center;margin:6px 0"><span style="width:90px">${esc(item.name)}</span><div class="bar" style="flex:1"><i style="width:${Math.min(item.share, 100)}%"></i></div><b>${item.share}%</b></div>`).join("");
  panel.innerHTML = `
    <h1>可见度总览 · ${esc(vis.brand_name)}</h1>
    <p class="sub">${esc(vis.compare_note || "")} · 样本 n=${vis.n_total}，有效 ${vis.n_valid}，排除 ${vis.n_excluded}，模拟/跳过 ${vis.n_mock}${vis.config_hash ? ` · hash ${esc(String(vis.config_hash).slice(0, 10))}` : ""}</p>
    <div class="grid g4" style="margin-bottom:16px">
      <div class="card kpi"><div class="l">K 类提及率（n=${vis.k.n_valid}）</div><div class="v">${rate(vis.k.mention_rate)}</div></div>
      <div class="card kpi"><div class="l">提及份额</div><div class="v">${rate(vis.k.share)}</div></div>
      <div class="card kpi"><div class="l">K 类推荐率</div><div class="v">${rate(vis.k.recommend_rate)}</div></div>
      <div class="card kpi"><div class="l">K 类首位率</div><div class="v">${rate(vis.k.first_rate)}</div><span class="l">D 类提及 ${rate(vis.d.mention_rate)}，不计入发现率</span></div>
    </div>
    <div class="grid g21">
      <div class="card"><h3>问题 × 引擎 <small>有效样本中的提及次数</small></h3><table class="hm"><tr><th>问题</th>${engines.map((engine) => `<th>${esc(engine)}</th>`).join("")}</tr>${matrix || "<tr><td>暂无矩阵</td></tr>"}</table></div>
      <div class="card"><h3>提及份额</h3>${share || "<p>有效样本里还没有可统计的提及。</p>"}</div>
    </div>
    <div class="card" style="margin-top:16px"><h3>方法</h3><p class="sub">${esc(vis.d.note)}。推荐和首位只统计通过原文校验的结果。模拟回答不进入上面的比率。</p>
      ${(vis.sentiment || []).map((item) => `<p><span class="tag">${esc(item.sentiment || "提及")}</span> ${esc(item.quote)}</p>`).join("")}
      <button class="btn sm" type="button" id="open-answers">查看回答</button>
    </div>`;
  panel.querySelector("#open-answers").onclick = () => openTab("answer", tab.projectId);
}

async function renderSources(tab, panel) {
  const data = await api(`/api/projects/${tab.projectId}/geo/sources`);
  panel.innerHTML = `<h1>引用来源 · ${esc(projectName(tab.projectId))}</h1><p class="sub">${esc(data.note)} · 自家占比 ${rate(data.own_share)} · 共 ${data.total} 条</p>
    <div class="card"><table><tr><th>域名</th><th>分类</th><th>次数</th><th>其中提及品牌</th></tr>${(data.domains || []).map((item) => `<tr><td>${esc(item.domain)}</td><td>${esc(item.category)}</td><td>${item.count}</td><td>${item.mentions_brand}</td></tr>`).join("") || "<tr><td colspan='4'>暂无</td></tr>"}</table></div>
    <div class="card" style="margin-top:16px"><h3>机会：竞品被引用、我方未出现</h3><table><tr><th>网址</th><th>次数</th></tr>${(data.gaps || []).map((item) => `<tr><td>${esc(item.url)}</td><td>${item.count}</td></tr>`).join("") || "<tr><td colspan='2'>暂无缺口</td></tr>"}</table>
    <p><button class="btn pri" type="button" id="to-plan">加入 30 天计划</button></p></div>`;
  panel.querySelector("#to-plan").onclick = async () => {
    try {
      const actions = await api(`/api/projects/${tab.projectId}/plan/suggest`, { method: "POST", body: "{}" });
      toast(actions.length ? `已放入 30 天计划（${actions.length} 条）` : "没有可加入的建议");
      openTab("plan", tab.projectId, undefined, {}, "plan");
    } catch (error) {
      toast(error.message);
    }
  };
}

async function renderAnswer(tab, panel) {
  if (!tab.extra.attemptId) {
    const attempts = await api(`/api/projects/${tab.projectId}/geo/attempts`);
    panel.innerHTML = `<h1>回答列表 · ${esc(projectName(tab.projectId))}</h1><div class="card"><table><tr><th>类型</th><th>问题</th><th>引擎</th><th>状态</th><th></th></tr>${attempts.map((item) => `<tr><td>${esc(item.probe_type)}</td><td>${esc(item.question)}</td><td>${esc(item.engine)}</td><td>${esc(item.status)} ${esc(item.error_code || "")}</td><td><button class="btn sm" type="button" data-attempt="${item.id}">打开</button></td></tr>`).join("") || "<tr><td colspan='5'>还没有采集尝试</td></tr>"}</table></div>`;
    panel.querySelectorAll("[data-attempt]").forEach((button) => {
      button.onclick = () => openTab("answer", tab.projectId, `回答 ${button.dataset.attempt}`, { attemptId: Number(button.dataset.attempt) });
    });
    return;
  }
  const detail = await api(`/api/geo/attempts/${tab.extra.attemptId}`);
  const attempt = detail.attempt;
  const response = detail.response;
  const skipped = attempt.status !== "ok";
  panel.innerHTML = `<h1>回答详情 · ${esc(attempt.engine)}</h1>
    <p><button class="btn sm" type="button" id="back-list">返回列表</button></p>
    <p class="sub">${esc(attempt.probe_type)} · ${esc(attempt.question)} · ${esc(attempt.access)} · ${esc(attempt.status)} ${esc(attempt.error_code || "")} · sha256 ${esc((attempt.payload_sha256 || "").slice(0, 12))}</p>
    ${skipped ? `<div class="card" style="border-color:#fde68a;background:#fffbeb;margin-bottom:16px"><b>本次未采到真实回答</b><p>${esc(reasonText(attempt))}</p><p class="sub">状态 ${esc(attempt.status)} · ${esc(attempt.error_code || "无错误码")} · 通道 ${esc(attempt.access)}</p></div>` : ""}
    <div class="grid g21"><div class="card"><h3>原始回答</h3><div style="white-space:pre-wrap;line-height:1.7">${esc(attempt.raw_response || "（无正文）")}</div>
      <h3 style="margin-top:12px">结构化引用</h3><table><tr><th>#</th><th>网址</th><th>分类</th></tr>${detail.citations.map((item) => `<tr><td>${item.position || ""}</td><td>${esc(item.url)}</td><td>${esc(item.category)}</td></tr>`).join("") || "<tr><td colspan='3'>无</td></tr>"}</table>
      <p>搜索词：${(attempt.web_queries || []).map((item) => `<span class="tag">${esc(item)}</span>`).join("") || "无"}</p></div>
      <div><div class="card"><h3>判定修订</h3>${detail.revisions.map((item) => `<p><span class="tag">${esc(item.reviewer)}</span> ${esc(item.parser_version)} · 有效 ${item.valid ? "是" : "否"}</p>`).join("") || "<p>无</p>"}</div>
      <div class="card" style="margin-top:16px"><h3>人工复核</h3>
        <label>品牌被提及</label><select id="rv-mentioned"><option value="true">是</option><option value="false">否</option></select>
        <label>位置</label><input id="rv-pos" value="${response && response.mention_position != null ? response.mention_position : ""}">
        <label>进入推荐</label><select id="rv-rec"><option value="false">否</option><option value="true">是</option></select>
        <label>备注</label><textarea id="rv-notes" rows="3"></textarea>
        <button class="btn pri" type="button" id="rv-save">确认复核</button></div></div></div>`;
  panel.querySelector("#back-list").onclick = () => openTab("answer", tab.projectId, undefined, {}, "answer");
  if (response) {
    panel.querySelector("#rv-mentioned").value = response.brand_mentioned ? "true" : "false";
    panel.querySelector("#rv-rec").value = response.recommended ? "true" : "false";
    panel.querySelector("#rv-save").onclick = async () => {
      await api(`/api/geo/responses/${response.id}/review`, {
        method: "PUT",
        body: JSON.stringify({
          brand_mentioned: panel.querySelector("#rv-mentioned").value === "true",
          mention_position: panel.querySelector("#rv-pos").value ? Number(panel.querySelector("#rv-pos").value) : null,
          recommended: panel.querySelector("#rv-rec").value === "true",
          competitor_mentions: response.competitor_mentions || [],
          cited_source: !!response.cited_source,
          reviewer_notes: panel.querySelector("#rv-notes").value,
          review_status: "reviewed",
        }),
      });
      toast("已写入人工修订");
      renderActive();
    };
  } else {
    panel.querySelector("#rv-save").disabled = true;
    panel.querySelector("#rv-notes").value = reasonText(attempt);
  }
}

function reasonText(attempt) {
  const code = attempt.error_code || "";
  if (code === "missing_api_key") return "未配置 API 密钥，本次没有发起真实请求。正文里的模拟说明不能当成联网结果。";
  if (code === "browser_stub") return "网页采集尚未实现。这条记录只表示计划中的抽样核对，没有打开浏览器。";
  if (code === "unsupported_engine") return "没有找到这个引擎对应的采集通道。";
  if (attempt.status === "error") return "采集通道返回错误，原始回答可能为空。";
  if (attempt.status !== "ok") return "本次没有拿到可用回答。";
  return "";
}

async function renderAssessment(tab, panel) {
  const data = await api(`/api/projects/${tab.projectId}/assessment`);
  panel.innerHTML = `<h1>评分与建议 · ${esc(projectName(tab.projectId))}</h1><p class="sub">${esc(data.scoring_note)}</p>
    <div class="grid g3"><div class="card kpi"><div class="l">综合</div><div class="v">${data.overall_score ?? "—"}</div></div><div class="card kpi"><div class="l">SEO</div><div class="v">${data.seo.score ?? "—"}</div></div><div class="card kpi"><div class="l">GEO</div><div class="v">${data.geo.score ?? "—"}</div></div></div>
    <div class="card" style="margin-top:16px"><h3>评分与建议</h3>${(data.recommendations || []).map((item) => `<p><b>${esc(item.dimension)} · ${esc(item.title)}</b><br>${esc(item.description)}</p>`).join("") || "<p>暂无缺口。</p>"}
    <button class="btn" type="button" id="to-kw">添加测试关键词</button></div>`;
  panel.querySelector("#to-kw").onclick = () => openTab("keywords", tab.projectId);
}

async function renderPlan(tab, panel) {
  let actions = await api(`/api/projects/${tab.projectId}/plan`);
  if (!actions.length) actions = await api(`/api/projects/${tab.projectId}/plan/suggest`, { method: "POST", body: "{}" });
  panel.innerHTML = `<h1>30 天改进计划 · ${esc(projectName(tab.projectId))}</h1>
    <p class="sub">行动项引用建议库的具体版本。升级建议不会改写已选用的版本。</p>
    <div class="card"><table><tr><th>优先级</th><th>行动</th><th>验收</th><th>状态</th><th>来源建议</th><th></th></tr>
      ${actions.map((item) => `<tr><td>${esc(item.priority)}</td><td>${esc(item.action)}</td><td>${esc(item.acceptance || "")}</td><td>${esc(item.status)}</td><td>${item.playbook_code ? `<button class="btn sm" type="button" data-pb="${item.playbook_version_id}" data-code="${esc(item.playbook_code)}">${esc(item.playbook_code)} v${item.playbook_version}</button>` : "自定义"}</td><td><button class="btn sm" type="button" data-outcome="${item.id}">记录结果</button></td></tr>`).join("") || "<tr><td colspan='6'>暂无行动</td></tr>"}
    </table></div>`;
  panel.querySelectorAll("[data-code]").forEach((button) => {
    button.onclick = async () => {
      const books = await api("/api/playbooks");
      const found = books.find((item) => item.code === button.dataset.code);
      if (found) openTab("playbook", null, found.code, { id: found.id });
    };
  });
  panel.querySelectorAll("[data-outcome]").forEach((button) => {
    button.onclick = async () => {
      const before = window.prompt("上期提及率（数字，可空）", "");
      const after = window.prompt("本期提及率（数字，可空）", "");
      await api(`/api/plan-actions/${button.dataset.outcome}/outcomes`, {
        method: "POST",
        body: JSON.stringify({
          before_value: before === "" || before == null ? null : Number(before),
          after_value: after === "" || after == null ? null : Number(after),
          note: "工作台手工回写",
        }),
      });
      toast("已回写效果");
    };
  });
}

async function renderReport(tab, panel) {
  const reports = await api(`/api/projects/${tab.projectId}/reports`);
  const plan = await api(`/api/projects/${tab.projectId}/plan`);
  panel.innerHTML = `<h1>报告预览 · ${esc(projectName(tab.projectId))}</h1>
    <p class="sub">报告冻结时所引用的建议版本会写进 HTML。D 类不代表自然发现率；引用不代表因果；API 与浏览器结果要分开看。</p>
    <div class="card"><p><button class="btn" type="button" id="preview">打开实时预览</button> <button class="btn pri" type="button" id="archive">归档当前报告</button></p>
      <iframe id="report-frame" hidden title="报告预览" style="width:100%;height:640px;border:1px solid var(--line);border-radius:12px;margin-top:12px;background:#fff"></iframe>
      <table><tr><th>标题</th><th>状态</th><th></th></tr>${reports.map((item) => `<tr><td>${esc(item.title)}</td><td>${esc(item.status)}</td><td><a href="/reports/${tab.projectId}/${item.id}" target="_blank">查看</a></td></tr>`).join("") || "<tr><td colspan='3'>尚未归档</td></tr>"}</table></div>
    <div class="card" style="margin-top:16px"><h3>将写入报告的行动</h3><table><tr><th>行动</th><th>建议版本</th><th>验收</th></tr>${plan.map((item) => `<tr><td>${esc(item.action)}</td><td>${esc(item.playbook_code || "自定义")} ${item.playbook_version ? "v" + item.playbook_version : ""}</td><td>${esc(item.acceptance || "")}</td></tr>`).join("") || "<tr><td colspan='3'>先在改进计划里选用建议</td></tr>"}</table></div>`;
  panel.querySelector("#preview").onclick = () => {
    const frame = panel.querySelector("#report-frame");
    frame.hidden = false;
    frame.src = `/reports/${tab.projectId}/preview`;
  };
  panel.querySelector("#archive").onclick = async () => {
    await api(`/api/projects/${tab.projectId}/reports`, { method: "POST", body: JSON.stringify({ title: `${projectName(tab.projectId)} GEO 可见度诊断` }) });
    toast("已归档");
    renderActive();
  };
}

async function renderPlaybooks(_tab, panel) {
  const books = await api("/api/playbooks");
  panel.innerHTML = `<h1>整改建议库</h1><p class="sub">模板可跨项目复用。选用时绑定版本；效果按版本回写，只说明相关、不证明因果。</p>
    <div class="card"><table><tr><th>编号</th><th>标题</th><th>类别</th><th>适用</th><th>版本</th><th>使用项目</th><th>平均变化</th><th>状态</th></tr>
      ${books.map((item) => `<tr><td><button class="btn sm" type="button" data-id="${item.id}" data-code="${esc(item.code)}">${esc(item.code)}</button></td><td>${esc(item.title)}</td><td>${esc(item.category)}</td><td>${esc(item.industries)} · ${esc(item.markets)}</td><td>v${item.latest_version}</td><td>${item.project_count}</td><td>${item.avg_delta == null ? "—" : item.avg_delta}</td><td><span class="tag ${item.status === "已发布" ? "t-ok" : item.status === "已废弃" ? "t-bad" : "t-warn"}">${esc(item.status)}</span></td></tr>`).join("")}
    </table></div>`;
  panel.querySelectorAll("[data-id]").forEach((button) => {
    button.onclick = () => openTab("playbook", null, button.dataset.code, { id: Number(button.dataset.id) });
  });
}

async function renderPlaybook(tab, panel) {
  if (!state.projects.length) await refreshProjects();
  const data = await api(`/api/playbooks/${tab.extra.id}`);
  const book = data.playbook;
  const current = data.versions[0];
  panel.innerHTML = `<h1>${esc(book.code)} ${esc(book.title)} <span class="tag">${esc(book.status)} · v${current ? current.version : ""}</span></h1>
    <div class="grid g21"><div class="card"><h3>触发条件</h3><p>${esc(current ? current.trigger_condition : "")}</p><h3>步骤</h3><pre style="white-space:pre-wrap">${esc(current ? current.steps : "")}</pre><h3>验收</h3><p>${esc(current ? current.acceptance_metric : "")}</p>
      <h3>版本</h3><table>${data.versions.map((item) => `<tr><td>v${item.version}</td><td>${esc(item.status)}</td><td>${esc(item.change_note || "")}</td></tr>`).join("")}</table>
      <button class="btn sm" type="button" id="upgrade">升级版本</button></div>
      <div class="card"><h3>加入计划</h3><p class="sub">把当前版本 v${current ? current.version : ""} 钉到所选项目的 30 天计划。之后升级建议不会改这条引用。</p>
        <label>项目</label><select id="plan-project">${state.projects.map((item) => `<option value="${item.id}">${esc(item.brand_name)} · ${esc(item.name)}</option>`).join("") || `<option value="">还没有项目</option>`}</select>
        <p><button class="btn pri" type="button" id="add-to-plan" ${current ? "" : "disabled"}>加入计划</button></p>
        <h3>关联项目</h3><table><tr><th>项目</th><th>版本</th><th>状态</th></tr>${data.actions.map((item) => `<tr><td>${esc(item.project_name)}</td><td>v${item.playbook_version}</td><td>${esc(item.status)}</td></tr>`).join("") || "<tr><td colspan='3'>还没有项目选用</td></tr>"}</table>
      <h3>效果回写</h3>${data.outcomes.map((item) => `<p>${esc(item.project_name)} v${item.playbook_version}：${item.delta == null ? "—" : item.delta}（n=${item.sample_n ?? "—"}）</p>`).join("") || "<p>暂无</p>"}</div></div>`;
  const addPlan = panel.querySelector("#add-to-plan");
  if (addPlan && current) addPlan.onclick = async () => {
    const projectId = Number(panel.querySelector("#plan-project").value);
    if (!projectId) { toast("请选择项目"); return; }
    try {
      await api(`/api/projects/${projectId}/plan-actions`, {
        method: "POST",
        body: JSON.stringify({
          playbook_version_id: current.id,
          priority: "P1",
          action: book.title,
          action_type: book.category || "",
          acceptance: current.acceptance_metric || "",
          status: "待开始",
        }),
      });
      toast(`已加入计划，绑定 v${current.version}`);
      state.projectId = projectId;
      syncSelect();
      openTab("plan", projectId, undefined, {}, "plan");
    } catch (error) {
      toast(error.message);
    }
  };
  panel.querySelector("#upgrade").onclick = async () => {
    const note = window.prompt("版本变更说明", "补充步骤");
    if (!note) return;
    await api(`/api/playbooks/${book.id}/versions`, {
      method: "POST",
      body: JSON.stringify({
        trigger_condition: current.trigger_condition,
        steps: current.steps,
        acceptance_metric: current.acceptance_metric,
        change_note: note,
        status: "草稿",
      }),
    });
    toast("已新增版本，旧引用不变");
    renderActive();
  };
}

async function renderChannels(_tab, panel) {
  const channels = await api("/api/geo/channels");
  const card = (item) => {
    if (item.kind === "web") {
      return `<div class="card"><h3>${esc(item.label)} <span class="tag t-warn">未实现</span> <span class="tag">${esc(item.phase)}</span></h3>
        <p class="sub">网页模拟通道尚未实现，测试连接不会打开浏览器。</p>
        <button class="btn sm" type="button" data-test="${esc(item.id)}">测试连接</button>
        <p class="sub">${esc(item.last_error || "")}</p></div>`;
    }
    const badge = item.status === "已连接" ? "t-ok" : item.status === "错误" ? "t-bad" : "t-warn";
    const placeholder = item.has_key ? `已保存 ****${item.key_last4}（${item.key_source === "env" ? "环境变量优先" : "服务器"}）` : "未填写";
    const secret = item.dual_key ? `<label>Secret Key</label><input id="secret-${esc(item.id)}" type="password" autocomplete="off" placeholder="${item.secret_last4 ? "已保存 ****" + esc(item.secret_last4) : "未填写"}">` : "";
    return `<div class="card"><h3>${esc(item.label)} <span class="tag ${badge}">${esc(item.status)}</span> <span class="tag">${esc(item.phase)}</span></h3>
      <p class="sub">引擎 ${esc(item.engine)} · 环境变量 ${(item.env_vars || []).map((name) => esc(name)).join(" / ") || "—"}</p>
      <label>启用</label><select id="en-${esc(item.id)}"><option value="1" ${item.enabled ? "selected" : ""}>启用</option><option value="0" ${item.enabled ? "" : "selected"}>停用</option></select>
      <label>API Key</label><input id="key-${esc(item.id)}" type="password" autocomplete="off" placeholder="${esc(placeholder)}">
      ${secret}
      <label>模型</label><input id="model-${esc(item.id)}" value="${esc(item.model || "")}">
      <label>联网搜索</label><select id="web-${esc(item.id)}"><option value="1" ${item.web_search ? "selected" : ""}>开</option><option value="0" ${item.web_search ? "" : "selected"}>关</option></select>
      <div class="grid g2"><div><label>地区</label><input id="region-${esc(item.id)}" value="${esc(item.region || "")}"></div><div><label>语言</label><input id="lang-${esc(item.id)}" value="${esc(item.language || "")}"></div></div>
      <div class="grid g2"><div><label>并发</label><input id="con-${esc(item.id)}" type="number" min="1" max="32" value="${item.concurrency}"></div><div><label>速率（次/分钟）</label><input id="rate-${esc(item.id)}" type="number" min="1" max="1000" value="${item.rate_limit_rpm}"></div></div>
      <label>单次预算上限（美元，可空）</label><input id="cap-${esc(item.id)}" type="number" min="0" step="0.01" value="${item.budget_cap_usd ?? ""}">
      <p class="sub">${item.last_tested_at ? `上次测试 ${esc(item.last_tested_at)} · ${item.last_latency_ms ?? "—"} ms` : "尚未测试"}${item.last_error ? ` · ${esc(item.last_error)}` : ""}</p>
      <p><button class="btn sm" type="button" data-save="${esc(item.id)}">保存</button>
      <button class="btn sm" type="button" data-test="${esc(item.id)}">测试连接</button>
      <button class="btn sm" type="button" data-clear="${esc(item.id)}">清除密钥</button></p></div>`;
  };
  panel.innerHTML = `<h1>采集通道</h1><p class="sub">每个官方 API 单独配置。密钥加密后只存服务器，页面只显示末四位；环境变量仍然优先。没有 SAG_SECRET_KEY 时不能保存新密钥。网页通道是 P1，尚未实现。</p><div class="channels">${channels.map(card).join("")}</div>`;
  const readChannel = (id) => {
    const cap = panel.querySelector(`#cap-${id}`).value.trim();
    const body = {
      enabled: panel.querySelector(`#en-${id}`).value === "1",
      model: panel.querySelector(`#model-${id}`).value,
      web_search: panel.querySelector(`#web-${id}`).value === "1",
      region: panel.querySelector(`#region-${id}`).value,
      language: panel.querySelector(`#lang-${id}`).value,
      concurrency: Number(panel.querySelector(`#con-${id}`).value),
      rate_limit_rpm: Number(panel.querySelector(`#rate-${id}`).value),
      budget_cap_usd: cap === "" ? null : Number(cap),
    };
    const key = panel.querySelector(`#key-${id}`);
    if (key && key.value.trim()) body.api_key = key.value.trim();
    const secret = panel.querySelector(`#secret-${id}`);
    if (secret && secret.value.trim()) body.api_secret = secret.value.trim();
    return body;
  };
  panel.querySelectorAll("[data-save]").forEach((button) => {
    button.onclick = async () => {
      try {
        await api(`/api/geo/channels/${button.dataset.save}`, { method: "PUT", body: JSON.stringify(readChannel(button.dataset.save)) });
        toast("已保存");
        renderActive();
      } catch (error) {
        toast(error.message);
      }
    };
  });
  panel.querySelectorAll("[data-clear]").forEach((button) => {
    button.onclick = async () => {
      try {
        await api(`/api/geo/channels/${button.dataset.clear}`, { method: "PUT", body: JSON.stringify({ clear_key: true }) });
        toast("已清除保存的密钥");
        renderActive();
      } catch (error) {
        toast(error.message);
      }
    };
  });
  panel.querySelectorAll("[data-test]").forEach((button) => {
    button.onclick = async () => {
      button.disabled = true;
      try {
        const result = await api(`/api/geo/channels/${button.dataset.test}/test`, { method: "POST", body: "{}" });
        toast(result.ok ? `已连接 ${result.latency_ms} ms` : `${result.status}${result.error ? "：" + result.error : ""}`);
        renderActive();
      } catch (error) {
        toast(error.message);
        button.disabled = false;
      }
    };
  });
}

async function renderCollection(_tab, panel) {
  const rows = await api("/api/geo/collection-catalog");
  panel.innerHTML = `<h1>采集方案总表</h1><p class="sub">P0 走官方 API。P1 浏览器采集只保留接口。密钥缺失时跳过，不会让任务崩溃。</p>
    <div class="card" style="overflow:auto"><table><tr><th>平台</th><th>方法</th><th>引用</th><th>阶段</th><th>风险</th><th>备注</th></tr>
      ${rows.map((item) => `<tr><td><b>${esc(item.platform)}</b></td><td>${esc(item.method)}</td><td>${esc(item.citations)}</td><td><span class="tag ${item.phase.startsWith("P0") ? "t-ok" : "t-warn"}">${esc(item.phase)}</span></td><td>${esc(item.risk)}</td><td>${esc(item.notes)}</td></tr>`).join("")}
    </table></div>`;
}

function renderArchitecture(_tab, panel) {
  panel.innerHTML = `<h1>技术架构</h1><p class="sub">在现有 FastAPI / SQLite 测评服务上扩展，不替换原来的客户、承诺、SEO 和报告接口。</p>
    <div class="card"><div class="arch">
      <div class="box"><b>工作台</b>左侧导航在右侧打开可关闭的标签。看板按项目打开。</div>
      <div class="box"><b>问题库</b>关键内容生成 D/K 问题，保存后可改。监测前冻结 config_hash。</div>
      <div class="box"><b>采集</b>OpenAI、Perplexity、Gemini、Claude、DeepSeek、Kimi，以及已有的 OpenRouter / 千帆。浏览器是 Playwright + Camoufox 的空接口。</div>
      <div class="box"><b>判定</b>LLM JSON 加本地原文校验。人工复核再写一条修订，不覆盖原文。</div>
      <div class="box"><b>建议库</b>playbooks / playbook_versions。计划行动引用版本，效果回写到 outcomes。</div>
    </div>
    <p class="sub" style="margin-top:12px">调度器只写入下次运行时间，没有常驻 cron。多租户登录和 Postgres 仍沿用后续计划。SQLite 继续作为当前库。</p></div>`;
}

async function renderKeywords(tab, panel) {
  const targets = await api(`/api/projects/${tab.projectId}/keyword-targets`);
  panel.innerHTML = `<h1>添加测试关键词 · ${esc(projectName(tab.projectId))}</h1>
    <div class="card"><div class="grid g3"><div><label>关键词</label><input id="kw"></div><div><label>引擎</label><select id="kw-engine"><option value="baidu">百度</option><option value="google">Google</option><option value="bing">Bing</option></select></div><div><label>地域</label><input id="kw-region" value="全国"></div></div>
    <p><button class="btn pri" type="button" id="kw-add">添加测试关键词</button></p>
    <table><tr><th>关键词</th><th>引擎</th><th>地域</th><th>语言</th></tr>${targets.map((item) => `<tr><td>${esc(item.keyword)}</td><td>${esc(item.engine)}</td><td>${esc(item.region_name)}</td><td>${esc(item.language)}</td></tr>`).join("") || "<tr><td colspan='4'>暂无</td></tr>"}</table></div>`;
  panel.querySelector("#kw-add").onclick = async () => {
    await api(`/api/projects/${tab.projectId}/keyword-targets`, {
      method: "POST",
      body: JSON.stringify({ keyword: panel.querySelector("#kw").value, engine: panel.querySelector("#kw-engine").value, region_name: panel.querySelector("#kw-region").value, language: "zh-CN" }),
    });
    toast("已添加");
    renderActive();
  };
}

const RENDER = {
  clients: renderClients,
  wizard: renderWizard,
  config: renderConfig,
  runs: renderRuns,
  dashboard: renderDashboard,
  sources: renderSources,
  answer: renderAnswer,
  assessment: renderAssessment,
  plan: renderPlan,
  report: renderReport,
  playbooks: renderPlaybooks,
  playbook: renderPlaybook,
  channels: renderChannels,
  collection: renderCollection,
  architecture: renderArchitecture,
  keywords: renderKeywords,
};

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".navbtn[data-page]").forEach((button) => {
    button.onclick = () => openTab(button.dataset.page, state.projectId, undefined, {}, button.dataset.nav || button.dataset.page);
  });
  document.querySelector("#new-project").onclick = () => openTab("wizard");
  document.querySelector("#seed-demo").onclick = async () => {
    try {
      const seeded = await api(DEMO_URL, { method: "POST", body: "{}" });
      await refreshProjects();
      state.projectId = seeded.project_id;
      syncSelect();
      openTab("dashboard", seeded.project_id, "看板 · 演示");
      toast(seeded.created ? "演示数据已创建" : "已打开现有演示项目");
    } catch (error) {
      toast(error.message);
    }
  };
  document.querySelector("#project-select").onchange = (event) => {
    state.projectId = Number(event.target.value) || null;
  };
  refreshProjects().then(() => openTab("clients")).catch((error) => toast(error.message));
});
