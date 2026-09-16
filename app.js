const DATA_URL = './data/processed/2026.json';

let seasonData = null;
let matchupChart = null;
let trendChart = null;
let chartMode = 'matchup';
let selectedWeek = null;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function fmtNumber(value, digits = 2) {
  return Number(value ?? 0).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtDate(iso) {
  if (!iso) return 'Not yet synced';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function safeLogo(url, name) {
  const fallback = `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=1b273b&color=f4f7fb&bold=true&format=svg`;
  return { src: url || fallback, fallback };
}

function teamLogoHTML(team, className = 'team-logo') {
  const logo = safeLogo(team.logo, team.teamName);
  return `<img class="${className}" src="${logo.src}" alt="" onerror="this.onerror=null;this.src='${logo.fallback}'">`;
}

function showError(message) {
  const toast = $('#errorToast');
  toast.textContent = message;
  toast.hidden = false;
}

function getFinalizedWeek(weekNum) {
  return seasonData?.weeks?.find((w) => w.week === Number(weekNum));
}

function getLastWeeklyRow(teamId) {
  const lastWeek = seasonData?.weeks?.at(-1);
  return lastWeek?.teams?.find((t) => t.teamId === teamId);
}

function renderHeader() {
  const sync = seasonData.sync;
  $('#syncText').textContent = `Final through W${sync.finalizedThroughWeek} · ${fmtDate(sync.syncedAt)}`;
  $('#overviewSubtitle').textContent = `Finalized through Week ${sync.finalizedThroughWeek}. Week ${sync.nextUnfinalizedWeek ?? '—'} is next.`;
}

function renderHeadlineStats() {
  const finalized = seasonData.sync.finalizedThroughWeek;
  const standings = seasonData.standings;
  const leaderVP = Math.max(...standings.map((t) => t.totalVP));
  const leaders = standings.filter((t) => t.totalVP === leaderVP);
  const topPF = [...standings].sort((a, b) => b.pointsFor - a.pointsFor)[0];
  const fourVP = standings.reduce((sum, t) => sum + t.fourVPWeeks, 0);

  const leaderLabel = leaders.length === 1 ? leaders[0].teamName : `${leaders.length}-way tie`;
  const cards = [
    ['Finalized Week', `W${finalized}`, `Next: Week ${seasonData.sync.nextUnfinalizedWeek ?? '—'}`],
    ['VP Leader', `${leaderVP} VP`, leaderLabel],
    ['Points Leader', fmtNumber(topPF.pointsFor), topPF.teamName],
    ['4-VP Weeks', `${fourVP}`, 'Perfect weekly outcomes'],
  ];

  $('#headlineStats').innerHTML = cards.map(([label, value, meta]) => `
    <article class="stat-card">
      <div class="stat-label">${label}</div>
      <div class="stat-value">${value}</div>
      <div class="stat-meta">${meta}</div>
    </article>
  `).join('');
}

function renderStandings() {
  $('#standingsBody').innerHTML = seasonData.standings.map((team) => {
    const last = getLastWeeklyRow(team.teamId);
    return `
      <tr>
        <td class="rank-cell">${team.vpRank}</td>
        <td class="team-cell">
          <div class="team-inline">
            ${teamLogoHTML(team)}
            <div>
              <span class="team-name">${team.teamName}</span>
              <span class="team-abbrev">${team.abbrev || ''}</span>
            </div>
          </div>
        </td>
        <td class="vp-cell">${team.totalVP}</td>
        <td>${team.record}</td>
        <td>${fmtNumber(team.pointsFor)}</td>
        <td>#${team.pointsForRank}</td>
        <td>${team.matchupVP}</td>
        <td>${team.scoringVP}</td>
        <td><span class="vp-mini">${last ? `+${last.weeklyVP}` : '—'}</span></td>
      </tr>
    `;
  }).join('');
}

function initWeekSelector() {
  const select = $('#weekSelect');
  select.innerHTML = seasonData.weeks.map((week) => `<option value="${week.week}">Week ${week.week}</option>`).join('');
  selectedWeek = seasonData.sync.finalizedThroughWeek;
  select.value = String(selectedWeek);
  select.addEventListener('change', () => {
    selectedWeek = Number(select.value);
    renderWeeklySection();
  });
}

function groupMatchupLabels(week) {
  const rows = week.teams;
  const used = new Set();
  const groups = [];
  rows.forEach((row) => {
    if (used.has(row.teamId)) return;
    const opp = rows.find((x) => x.teamId === row.opponentId);
    if (!opp) return;
    used.add(row.teamId);
    used.add(opp.teamId);
    groups.push([row, opp]);
  });
  return groups;
}

const scoringZonesPlugin = {
  id: 'scoringZones',
  beforeDraw(chart, args, opts) {
    if (!opts?.top3 || !opts?.top6) return;
    const { ctx, chartArea, scales } = chart;
    if (!chartArea) return;
    const y = scales.y;
    const yTop3 = y.getPixelForValue(opts.top3);
    const yTop6 = y.getPixelForValue(opts.top6);
    ctx.save();
    ctx.fillStyle = 'rgba(82,214,184,.055)';
    ctx.fillRect(chartArea.left, chartArea.top, chartArea.right - chartArea.left, yTop3 - chartArea.top);
    ctx.fillStyle = 'rgba(244,185,66,.045)';
    ctx.fillRect(chartArea.left, yTop3, chartArea.right - chartArea.left, yTop6 - yTop3);
    ctx.fillStyle = 'rgba(159,176,199,.025)';
    ctx.fillRect(chartArea.left, yTop6, chartArea.right - chartArea.left, chartArea.bottom - yTop6);

    ctx.setLineDash([6, 5]);
    ctx.lineWidth = 1;
    ctx.strokeStyle = 'rgba(82,214,184,.65)';
    ctx.beginPath(); ctx.moveTo(chartArea.left, yTop3); ctx.lineTo(chartArea.right, yTop3); ctx.stroke();
    ctx.strokeStyle = 'rgba(244,185,66,.58)';
    ctx.beginPath(); ctx.moveTo(chartArea.left, yTop6); ctx.lineTo(chartArea.right, yTop6); ctx.stroke();
    ctx.restore();
  },
};
Chart.register(scoringZonesPlugin);

function buildChartRows(week) {
  if (chartMode === 'scoring') {
    return [...week.teams].sort((a, b) => b.points - a.points);
  }
  return groupMatchupLabels(week).flatMap((pair) => pair);
}

function renderMatchupChart() {
  const week = getFinalizedWeek(selectedWeek);
  if (!week) return;

  const rows = buildChartRows(week);
  const labels = rows.map((r) => r.abbrev || r.teamName.slice(0, 6));
  const values = rows.map((r) => r.points);
  const bg = rows.map((r) => r.result === 'W' ? 'rgba(82,214,184,.82)' : 'rgba(110,168,254,.45)');
  const border = rows.map((r) => r.result === 'W' ? 'rgba(82,214,184,1)' : 'rgba(110,168,254,.72)');

  if (matchupChart) matchupChart.destroy();
  matchupChart = new Chart($('#matchupChart'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Points',
        data: values,
        backgroundColor: bg,
        borderColor: border,
        borderWidth: 1,
        borderRadius: 7,
        maxBarThickness: 42,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'nearest', intersect: true },
      onClick(event, elements) {
        if (!elements.length) return;
        renderTeamDetail(rows[elements[0].index], week);
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title(items) {
              const row = rows[items[0].dataIndex];
              return row.teamName;
            },
            label(ctx) {
              const row = rows[ctx.dataIndex];
              return `${fmtNumber(row.points)} pts · #${row.scoringRank} scoring · +${row.weeklyVP} VP`;
            },
            afterLabel(ctx) {
              const row = rows[ctx.dataIndex];
              return `${row.result} vs ${row.opponentName}`;
            },
          },
        },
        scoringZones: { top3: week.top3Cutoff, top6: week.top6Cutoff },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#9fb0c7', font: { size: 10, weight: '700' }, maxRotation: 0, minRotation: 0 },
          border: { color: 'rgba(255,255,255,.07)' },
        },
        y: {
          beginAtZero: true,
          grace: '12%',
          ticks: { color: '#6f829c', font: { size: 10 } },
          grid: { color: 'rgba(255,255,255,.055)' },
          border: { display: false },
        },
      },
    },
  });
}

function renderTeamDetail(row, week) {
  const team = seasonData.standings.find((t) => t.teamId === row.teamId) || row;
  const brutal = row.result === 'L' && row.scoringRank <= 3;
  const survived = row.result === 'W' && row.scoringRank >= 7;
  let tag = '';
  if (brutal) tag = '<span class="result-badge result-loss">💀 Brutal Loss</span>';
  else if (survived) tag = '<span class="result-badge result-win">😅 Survived</span>';
  else tag = `<span class="result-badge ${row.result === 'W' ? 'result-win' : 'result-loss'}">${row.result === 'W' ? 'W' : 'L'} vs ${row.opponentName}</span>`;

  $('#teamDetail').innerHTML = `
    <div class="detail-head">
      ${teamLogoHTML(team)}
      <div>
        <h3>${row.teamName}</h3>
        <p>Week ${week.week} · ${team.abbrev || ''}</p>
      </div>
    </div>
    ${tag}
    <div class="detail-score">${fmtNumber(row.points)}</div>
    <div class="detail-rank">League scoring rank #${row.scoringRank} · Opponent ${fmtNumber(row.opponentPoints)}</div>
    <div class="detail-vp-grid">
      <div class="detail-vp-item"><strong>+${row.matchupVP}</strong><span>Match VP</span></div>
      <div class="detail-vp-item"><strong>+${row.scoringVP}</strong><span>Score VP</span></div>
      <div class="detail-vp-item"><strong>#${row.scoringRank}</strong><span>Score Rank</span></div>
    </div>
    <div class="detail-total"><span>Week ${week.week} total</span><strong>+${row.weeklyVP} VP</strong></div>
  `;
}

function renderWeeklyHighlights() {
  const week = getFinalizedWeek(selectedWeek);
  if (!week) return;
  const rows = [...week.teams];
  const high = [...rows].sort((a,b) => b.points-a.points)[0];
  const low = [...rows].sort((a,b) => a.points-b.points)[0];
  const closest = [...rows]
    .filter((r) => r.teamId < r.opponentId)
    .map((r) => ({ row: r, margin: Math.abs(r.points-r.opponentPoints) }))
    .sort((a,b) => a.margin-b.margin)[0];
  const brutal = rows.find((r) => r.result === 'L' && r.scoringRank <= 3);
  const survivor = rows.find((r) => r.result === 'W' && r.scoringRank >= 7);
  const fourth = rows.filter((r) => r.weeklyVP === 4).length;

  const cards = [
    ['👑', 'Top Scorer', high.teamName, `${fmtNumber(high.points)} points`],
    ['🤏', 'Closest Matchup', closest?.row.teamName || '—', closest ? `${fmtNumber(closest.margin)}-pt margin` : '—'],
    ['💀', 'Brutal Loss', brutal?.teamName || 'None', brutal ? `#${brutal.scoringRank} scorer still lost` : 'No top-3 scorer lost'],
    ['😅', 'Survivor', survivor?.teamName || 'None', survivor ? `Won from scoring rank #${survivor.scoringRank}` : `${fourth} perfect 4-VP week${fourth === 1 ? '' : 's'}`],
  ];
  $('#weeklyHighlights').innerHTML = cards.map(([icon,label,value,meta]) => `
    <article class="highlight-card">
      <div class="icon">${icon}</div>
      <div class="label">${label}</div>
      <div class="value">${value}</div>
      <div class="meta">${meta}</div>
    </article>
  `).join('');
}

function renderWeeklySection() {
  renderMatchupChart();
  renderWeeklyHighlights();
  const week = getFinalizedWeek(selectedWeek);
  if (week?.teams?.length) renderTeamDetail(week.teams[0], week);
}

function linePalette(index, alpha = 1) {
  const hue = (index * 43 + 22) % 360;
  return `hsla(${hue}, 75%, 64%, ${alpha})`;
}

function renderTrendChart() {
  const weeks = seasonData.weeks.map((w) => `W${w.week}`);
  const datasets = seasonData.standings.map((team, i) => ({
    label: team.teamName,
    data: team.rankHistory.map((x) => x.vp),
    borderColor: linePalette(i),
    backgroundColor: linePalette(i, .12),
    borderWidth: 2,
    pointRadius: 3,
    pointHoverRadius: 5,
    tension: .22,
  }));
  if (trendChart) trendChart.destroy();
  trendChart = new Chart($('#vpTrendChart'), {
    type: 'line',
    data: { labels: weeks, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'nearest', intersect: false },
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#9fb0c7', boxWidth: 10, usePointStyle: true, pointStyle: 'circle', padding: 14, font: { size: 10 } },
        },
        tooltip: { mode: 'index', intersect: false },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#6f829c' }, border: { color: 'rgba(255,255,255,.07)' } },
        y: { beginAtZero: true, ticks: { color: '#6f829c', precision: 0 }, grid: { color: 'rgba(255,255,255,.055)' }, border: { display: false } },
      },
    },
  });
}

function renderTeamGrid() {
  $('#teamGrid').innerHTML = seasonData.standings.map((team) => `
    <article class="team-card">
      <div class="team-card-head">
        ${teamLogoHTML(team)}
        <div style="min-width:0">
          <div class="team-card-name">${team.teamName}</div>
          <div class="team-card-rank">VP rank #${team.vpRank} · PF rank #${team.pointsForRank}</div>
        </div>
      </div>
      <div class="team-card-stats">
        <div class="team-card-stat"><strong>${team.totalVP}</strong><span>VP</span></div>
        <div class="team-card-stat"><strong>${team.record}</strong><span>Record</span></div>
        <div class="team-card-stat"><strong>${fmtNumber(team.pointsFor, 0)}</strong><span>PF</span></div>
      </div>
    </article>
  `).join('');
}

function initNavigation() {
  $$('.nav-link').forEach((btn) => {
    btn.addEventListener('click', () => {
      const target = document.getElementById(btn.dataset.target);
      if (!target) return;
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  const sections = $$('.section-block');
  const observer = new IntersectionObserver((entries) => {
    const visible = entries.filter((e) => e.isIntersecting).sort((a,b) => b.intersectionRatio-a.intersectionRatio)[0];
    if (!visible) return;
    $$('.nav-link').forEach((btn) => btn.classList.toggle('active', btn.dataset.target === visible.target.id));
  }, { threshold: [0.2, 0.45], rootMargin: '-80px 0px -50% 0px' });
  sections.forEach((section) => observer.observe(section));
}

function initChartModeToggle() {
  $$('.segment').forEach((btn) => {
    btn.addEventListener('click', () => {
      chartMode = btn.dataset.chartMode;
      $$('.segment').forEach((b) => b.classList.toggle('active', b === btn));
      renderWeeklySection();
    });
  });
}

async function loadData() {
  try {
    const response = await fetch(`${DATA_URL}?v=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    seasonData = await response.json();
  } catch (error) {
    console.error(error);
    showError('Could not load processed league data. Run the ESPN Data Pipeline workflow and refresh.');
    return;
  }

  renderHeader();
  renderHeadlineStats();
  renderStandings();
  initWeekSelector();
  renderWeeklySection();
  renderTrendChart();
  renderTeamGrid();
}

initNavigation();
initChartModeToggle();
loadData();
