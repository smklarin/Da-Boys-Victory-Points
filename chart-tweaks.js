// V1.1 weekly chart refinements.
// Loaded after app.js so this replaces the initial chart renderer while
// preserving the rest of the dashboard logic.

function weeklyScoringBoundaries(week) {
  const ranked = [...week.teams].sort((a, b) => b.points - a.points);
  return {
    top3: (ranked[2].points + ranked[3].points) / 2,
    top6: (ranked[5].points + ranked[6].points) / 2,
  };
}

function applyScoringZonePalette() {
  // Keep matchup outcomes and scoring tiers visually distinct:
  // winner = green, loss = blue, +2 VP = gold, +1 VP = coral, +0 VP = gray.
  const twoVpSwatch = document.querySelector('.zone-two');
  const oneVpSwatch = document.querySelector('.zone-one');
  const zeroVpSwatch = document.querySelector('.zone-zero');

  if (twoVpSwatch) twoVpSwatch.style.background = 'rgba(244,185,66,.90)';
  if (oneVpSwatch) oneVpSwatch.style.background = 'rgba(239,106,120,.90)';
  if (zeroVpSwatch) zeroVpSwatch.style.background = 'rgba(159,176,199,.45)';
}

// Override the original scoring-zone drawing palette from app.js while
// preserving the same plugin registration and midpoint boundaries.
scoringZonesPlugin.beforeDraw = function beforeDraw(chart, args, opts) {
  if (!opts?.top3 || !opts?.top6) return;
  const { ctx, chartArea, scales } = chart;
  if (!chartArea) return;

  const y = scales.y;
  const yTop3 = y.getPixelForValue(opts.top3);
  const yTop6 = y.getPixelForValue(opts.top6);

  ctx.save();

  // +2 scoring VP zone: gold
  ctx.fillStyle = 'rgba(244,185,66,.085)';
  ctx.fillRect(
    chartArea.left,
    chartArea.top,
    chartArea.right - chartArea.left,
    yTop3 - chartArea.top,
  );

  // +1 scoring VP zone: coral
  ctx.fillStyle = 'rgba(239,106,120,.065)';
  ctx.fillRect(
    chartArea.left,
    yTop3,
    chartArea.right - chartArea.left,
    yTop6 - yTop3,
  );

  // +0 scoring VP zone: neutral gray
  ctx.fillStyle = 'rgba(159,176,199,.025)';
  ctx.fillRect(
    chartArea.left,
    yTop6,
    chartArea.right - chartArea.left,
    chartArea.bottom - yTop6,
  );

  ctx.setLineDash([6, 5]);
  ctx.lineWidth = 1;

  // Boundary between +2 and +1 scoring VP
  ctx.strokeStyle = 'rgba(244,185,66,.80)';
  ctx.beginPath();
  ctx.moveTo(chartArea.left, yTop3);
  ctx.lineTo(chartArea.right, yTop3);
  ctx.stroke();

  // Boundary between +1 and +0 scoring VP
  ctx.strokeStyle = 'rgba(239,106,120,.76)';
  ctx.beginPath();
  ctx.moveTo(chartArea.left, yTop6);
  ctx.lineTo(chartArea.right, yTop6);
  ctx.stroke();

  ctx.restore();
};

function ensureMatchupOutcomeLegend() {
  const legend = document.querySelector('.zone-legend');
  if (!legend || document.querySelector('.matchup-outcome-legend')) return;

  const winner = document.createElement('span');
  winner.className = 'matchup-outcome-legend';
  winner.innerHTML = '<i class="legend-swatch" style="background:rgba(82,214,184,.82)"></i> Matchup winner';

  const loser = document.createElement('span');
  loser.className = 'matchup-outcome-legend';
  loser.innerHTML = '<i class="legend-swatch" style="background:rgba(110,168,254,.45)"></i> Matchup loss';

  legend.append(winner, loser);
}

function setMatchupLegendVisibility() {
  applyScoringZonePalette();
  ensureMatchupOutcomeLegend();
  document.querySelectorAll('.matchup-outcome-legend').forEach((item) => {
    item.style.display = chartMode === 'matchup' ? 'inline-flex' : 'none';
  });

  const hint = document.querySelector('.chart-hint');
  if (hint) {
    hint.textContent = chartMode === 'matchup'
      ? 'Teams sharing the same M# are opponents. Tap or click any bar for the full VP breakdown.'
      : 'Teams are sorted from highest to lowest score. Tap or click any bar for the full VP breakdown.';
  }
}

function buildGroupedMatchupItems(week) {
  const items = [];
  const groups = groupMatchupLabels(week);

  groups.forEach((pair, index) => {
    const matchupNumber = index + 1;
    pair.forEach((row) => {
      items.push({
        row,
        matchupNumber,
        label: [row.abbrev || row.teamName.slice(0, 6), `M${matchupNumber}`],
        spacer: false,
      });
    });

    if (index < groups.length - 1) {
      items.push({ row: null, matchupNumber: null, label: '', spacer: true });
    }
  });

  return items;
}

function buildScoringItems(week) {
  return [...week.teams]
    .sort((a, b) => b.points - a.points)
    .map((row) => ({
      row,
      matchupNumber: null,
      label: row.abbrev || row.teamName.slice(0, 6),
      spacer: false,
    }));
}

function renderMatchupChart() {
  const week = getFinalizedWeek(selectedWeek);
  if (!week) return;

  setMatchupLegendVisibility();

  const boundaries = weeklyScoringBoundaries(week);
  const items = chartMode === 'matchup'
    ? buildGroupedMatchupItems(week)
    : buildScoringItems(week);

  const labels = items.map((item) => item.label);
  const values = items.map((item) => item.row ? item.row.points : null);
  const bg = items.map((item) => {
    if (!item.row) return 'rgba(0,0,0,0)';
    return item.row.result === 'W'
      ? 'rgba(82,214,184,.82)'
      : 'rgba(110,168,254,.45)';
  });
  const border = items.map((item) => {
    if (!item.row) return 'rgba(0,0,0,0)';
    return item.row.result === 'W'
      ? 'rgba(82,214,184,1)'
      : 'rgba(110,168,254,.72)';
  });

  if (matchupChart) matchupChart.destroy();
  matchupChart = new Chart(document.querySelector('#matchupChart'), {
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
        maxBarThickness: 44,
        categoryPercentage: chartMode === 'matchup' ? 0.92 : 0.8,
        barPercentage: chartMode === 'matchup' ? 0.94 : 0.9,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'nearest', intersect: true },
      onClick(event, elements) {
        if (!elements.length) return;
        const item = items[elements[0].index];
        if (!item?.row) return;
        renderTeamDetail(item.row, week);
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          filter(context) {
            return Boolean(items[context.dataIndex]?.row);
          },
          callbacks: {
            title(tooltipItems) {
              const item = items[tooltipItems[0].dataIndex];
              return item?.row?.teamName || '';
            },
            label(context) {
              const row = items[context.dataIndex]?.row;
              if (!row) return '';
              return `${fmtNumber(row.points)} pts · #${row.scoringRank} scoring · +${row.weeklyVP} VP`;
            },
            afterLabel(context) {
              const row = items[context.dataIndex]?.row;
              if (!row) return '';
              return `${row.result} vs ${row.opponentName}`;
            },
          },
        },
        scoringZones: {
          top3: boundaries.top3,
          top6: boundaries.top6,
        },
      },
      scales: {
        x: {
          offset: true,
          grid: { display: false },
          ticks: {
            color: '#9fb0c7',
            font: { size: 10, weight: '700' },
            maxRotation: 0,
            minRotation: 0,
            autoSkip: false,
          },
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
