import { useState, useEffect, useRef, useCallback } from 'react';
import { createChart, CandlestickSeries, createSeriesMarkers, LineStyle } from 'lightweight-charts';
import { 
  Play, Square, Settings as SettingsIcon, Activity, History, 
  BarChart3, RefreshCw, Key, ShieldAlert, Cpu, CheckCircle2, 
  TrendingUp, DollarSign, AlertCircle 
} from 'lucide-react';

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT"];
const TIMEFRAMES = ["1m", "3m", "5m", "15m", "1h", "4h", "1d"];
const DEFAULT_INITIAL_BALANCE = 1600.0;

// SMC Chart Component using Lightweight Charts
function SMCChart({ data, structures, activeTrade, symbol, timeframe }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || !data || data.length === 0) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: '#0c0d13' },
        textColor: '#9ca3af',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.03)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.03)' },
      },
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.08)',
      },
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.08)',
        timeVisible: true,
        secondsVisible: false,
      },
      width: containerRef.current.clientWidth,
      height: 380,
    });

    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    });

    // Format historical data
    const formattedData = data.map(d => ({
      time: d.timestamp ? Math.floor(d.timestamp / 1000) : Math.floor(new Date(d.time).getTime() / 1000),
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    // Remove duplicates
    const uniqueData = [];
    const seenTimes = new Set();
    for (const d of formattedData) {
      if (!seenTimes.has(d.time)) {
        seenTimes.add(d.time);
        uniqueData.push(d);
      }
    }
    uniqueData.sort((a, b) => a.time - b.time);

    candleSeries.setData(uniqueData);

    // Add markers
    const markers = [];
    if (structures) {
      if (structures.bos) {
        structures.bos.forEach(b => {
          markers.push({
            time: Math.floor(b.time / 1000),
            position: b.type === 'bullish' ? 'aboveBar' : 'belowBar',
            color: b.type === 'bullish' ? '#10b981' : '#ef4444',
            shape: 'arrowDown',
            text: `BOS ${b.type === 'bullish' ? '▲' : '▼'}`,
          });
        });
      }
      if (structures.choch) {
        structures.choch.forEach(c => {
          markers.push({
            time: Math.floor(c.time / 1000),
            position: c.type === 'bullish' ? 'aboveBar' : 'belowBar',
            color: '#a78bfa',
            shape: 'arrowDown',
            text: `CHoCH ${c.type === 'bullish' ? '▲' : '▼'}`,
          });
        });
      }
      if (structures.sweeps) {
        structures.sweeps.forEach(s => {
          markers.push({
            time: Math.floor(s.time / 1000),
            position: s.type === 'bullish_sweep' ? 'belowBar' : 'aboveBar',
            color: '#14b8a6',
            shape: s.type === 'bullish_sweep' ? 'arrowUp' : 'arrowDown',
            text: 'SWEEP 🧹',
          });
        });
      }
    }

    markers.sort((a, b) => a.time - b.time);
    const validMarkers = markers.filter(m => seenTimes.has(m.time));
    createSeriesMarkers(candleSeries, validMarkers);

    if (uniqueData.length > 30) {
      chart.timeScale().setVisibleLogicalRange({
        from: uniqueData.length - 30,
        to: uniqueData.length + 3
      });
    } else {
      chart.timeScale().fitContent();
    }

    // Draw active trade lines if present
    if (activeTrade) {
      const entryPrice = parseFloat(activeTrade.entry_price);
      const slPrice = parseFloat(activeTrade.sl);
      const tpPrice = parseFloat(activeTrade.tp);

      candleSeries.createPriceLine({
        price: entryPrice,
        color: '#3b82f6', // Blue for entry
        lineWidth: 1.5,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: `ENTRY: $${formatPrice(entryPrice)}`,
      });

      candleSeries.createPriceLine({
        price: slPrice,
        color: '#ef4444', // Red for stop loss
        lineWidth: 1.5,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: `SL: $${formatPrice(slPrice)}`,
      });

      candleSeries.createPriceLine({
        price: tpPrice,
        color: '#10b981', // Green for take profit
        lineWidth: 1.5,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: `TP: $${formatPrice(tpPrice)}`,
      });
    }

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [data, structures, activeTrade, symbol, timeframe]);
  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.04)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontWeight: 700, color: 'var(--text-main)' }}>{symbol || 'UNKNOWN'}</div>
        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{timeframe || ''}</div>
      </div>
      <div ref={containerRef} style={{ width: '100%', height: '380px' }} />
    </div>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState('live'); // 'live' | 'backtest'
  
  // Live Bot States
  const [botRunning, setBotRunning] = useState(false);
  const [botTimeframe, setBotTimeframe] = useState('15m');
  const [balance, setBalance] = useState(DEFAULT_INITIAL_BALANCE);
  const [initialBalance, setInitialBalance] = useState(DEFAULT_INITIAL_BALANCE);
  const [activeTrades, setActiveTrades] = useState({});
  const [scannedSymbolsStatus, setScannedSymbolsStatus] = useState({});
  const [scanCount, setScanCount] = useState(0);
  const [scanTotal, setScanTotal] = useState(0);
  const [scanSkipped, setScanSkipped] = useState(0);
  const [signalsFound, setSignalsFound] = useState(0);
  const [openTradesCreated, setOpenTradesCreated] = useState(0);
  const [scanCycleCount, setScanCycleCount] = useState(0);
  const [nextScanCountdown, setNextScanCountdown] = useState(15);
  const [scanIntervalSeconds, setScanIntervalSeconds] = useState(15);
  const [scanLastBroadcastAt, setScanLastBroadcastAt] = useState(Date.now());
  const [isScanning, setIsScanning] = useState(false);
  const [selectedSymbol, setSelectedSymbol] = useState('BTCUSDT');
  const [tradeHistory, setTradeHistory] = useState([]);
  const [latestPrice, setLatestPrice] = useState(0.0);
  const [latestTrend, setLatestTrend] = useState('neutral');
  const activePositionsPnl = Object.entries(activeTrades).reduce((sum, [symbol, trade]) => {
    const unrealized = trade.unrealized_pnl !== undefined && trade.unrealized_pnl !== null
      ? parseFloat(trade.unrealized_pnl) || 0
      : 0;
    if (unrealized !== 0) {
      return sum + unrealized;
    }
    const markPrice = parseFloat(trade.mark_price) || 0;
    const currentPrice = markPrice > 0
      ? markPrice
      : symbol === selectedSymbol
        ? latestPrice || scannedSymbolsStatus[symbol]?.price || trade.entry_price || 0
        : scannedSymbolsStatus[symbol]?.price || trade.entry_price || 0;
    const entryPrice = parseFloat(trade.entry_price) || 0;
    const size = parseFloat(trade.size) || 0;
    const pnl = trade.type === 'short'
      ? (entryPrice - currentPrice) * size
      : (currentPrice - entryPrice) * size;
    return sum + pnl;
  }, 0);
  const totalPnl = activePositionsPnl;
  const totalPnlPct = initialBalance > 0 ? (totalPnl / initialBalance) * 100 : 0;
  const formattedTotalPnl = `${totalPnl >= 0 ? '+' : ''}${totalPnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const formattedTotalPnlPct = `${totalPnlPct >= 0 ? '+' : ''}${totalPnlPct.toFixed(2)}%`;
  const [logs, setLogs] = useState([]);
  const [apiError, setApiError] = useState(null);
  const [binanceAuthStatus, setBinanceAuthStatus] = useState('unknown');
  const [binanceAuthSource, setBinanceAuthSource] = useState(null);
  const [binanceAuthMode, setBinanceAuthMode] = useState(null);
  const [binanceAuthMessage, setBinanceAuthMessage] = useState(null);
  const [websocketStatus, setWebsocketStatus] = useState('disconnected');
  const [websocketUrl, setWebsocketUrl] = useState('');
  
  const [statusLoaded, setStatusLoaded] = useState(false);
  const [websocketErrorMessage, setWebsocketErrorMessage] = useState(null);
  
  // Configuration State
  const [config, setConfig] = useState({
    binance_api_key: '',
    binance_api_secret: '',
    testnet: true,
    trading_mode: 'paper',
    market_type: 'futures',
    symbol: 'BTCUSDT',
    timeframe: '15m',
    risk_pct: 1.0,
    rr_ratio: 2.0,
    n_swing: 2,
    x_impulse: 2.0,
    m_range: 5,
    breakeven_trigger: 1.0,
    peak_drawdown_exit_pct: 4.0,
    portfolio_margin: false,
    max_trade_loss_usd: 35.0
  });

  // Backtest States
  const [backtestConfig, setBacktestConfig] = useState({
    symbol: 'BTCUSDT',
    timeframe: '15m',
    initial_balance: DEFAULT_INITIAL_BALANCE,
    risk_pct: 1.0,
    rr_ratio: 2.0,
    n_swing: 2,
    x_impulse: 2.0,
    m_range: 5,
    breakeven_trigger: 1.0,
    limit: 500
  });
  const [backtestResults, setBacktestResults] = useState(null);
  const [backtesting, setBacktesting] = useState(false);

  // Live Chart States
  const [liveChartData, setLiveChartData] = useState([]);
  const [liveStructures, setLiveStructures] = useState(null);

  // References
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const reconnectAttemptRef = useRef(0);
  const shouldReconnectRef = useRef(true);
  const logsEndRef = useRef(null);
  const consoleContainerRef = useRef(null);
  const fetchStatusRef = useRef(null);
  const fetchTradesRef = useRef(null);
  const heartbeatTimerRef = useRef(null);

  // Use a direct backend websocket URL in local development when possible.
  // Otherwise proxy websocket traffic through the frontend host.
  const websocketProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const isLocalDevHost = ['127.0.0.1', 'localhost'].includes(window.location.hostname);
  const websocketDirectUrl = isLocalDevHost ? `${websocketProtocol}://127.0.0.1:8005/api/ws` : null;
  const websocketProxyUrl = `${websocketProtocol}://${window.location.host}/api/ws`;
  const lastTriedDirectRef = useRef(false);

  const safeFetchJson = useCallback(async (url, options = {}, fallback = null) => {
    try {
      const res = await fetch(url, options);
      if (!res.ok) {
        console.warn(`Request failed (${res.status}): ${url}`);
        return fallback;
      }
      const contentType = res.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) {
        console.warn(`Unexpected content type for ${url}: ${contentType}`);
        return fallback;
      }
      return await res.json();
    } catch (err) {
      console.warn(`Network error while fetching ${url}`, err);
      return fallback;
    }
  }, []);

  const fetchLiveChart = useCallback(async (symbolToFetch) => {
    const sym = symbolToFetch || selectedSymbol || 'BTCUSDT';
    const data = await safeFetchJson(`/chart?symbol=${sym}`, {}, { chart_data: [], structures: {} });
    if (!data) {
      return;
    }
    setLiveChartData(data.chart_data || []);
    setLiveStructures(data.structures || {});
  }, [selectedSymbol, safeFetchJson]);

  const showNotification = useCallback((title, body) => {
    if ('Notification' in window && Notification.permission === 'granted') {
      try {
        new Notification(title, {
          body,
          icon: '/favicon.svg'
        });
      } catch (err) {
        console.error('Notification failed', err);
      }
    }
  }, []);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const clearHeartbeatTimer = useCallback(() => {
    if (heartbeatTimerRef.current) {
      window.clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
  }, []);

  const connectWebSocket = useCallback(function connect(useDirect) {
    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) {
      wsRef.current.close();
    }
    clearReconnectTimer();

    const useDirectConnection = typeof useDirect === 'boolean' ? useDirect : Boolean(websocketDirectUrl);
    const targetUrl = useDirectConnection && websocketDirectUrl ? websocketDirectUrl : websocketProxyUrl;
    lastTriedDirectRef.current = targetUrl === websocketDirectUrl;
    setWebsocketUrl(targetUrl);
    try {
      console.debug('[WebSocket] connecting to', targetUrl);
    } catch (e) {}
    setWebsocketStatus('connecting');

    const ws = new WebSocket(targetUrl);
    wsRef.current = ws;
    wsRef.currentUrl = targetUrl;

    ws.onopen = () => {
      clearReconnectTimer();
      clearHeartbeatTimer();
      reconnectAttemptRef.current = 0;
      setWebsocketStatus('open');
      setWebsocketErrorMessage(null);
      console.debug('[WebSocket] connection opened', targetUrl);
      fetchStatusRef.current?.();
      fetchTradesRef.current?.();

      heartbeatTimerRef.current = window.setInterval(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          try {
            wsRef.current.send(JSON.stringify({ type: 'ping', ts: Date.now() }));
          } catch (err) {
            console.debug('[WebSocket] heartbeat failed', err);
          }
        }
      }, 25000);
    };

    ws.onerror = (event) => {
      console.debug('[WebSocket] error', event, 'url=', targetUrl);
      setWebsocketStatus('error');
      const errMsg = event?.message ? String(event.message) : `WebSocket connection error (${targetUrl})`;
      const attempt = (reconnectAttemptRef.current || 0) + 1;
      reconnectAttemptRef.current = attempt;
      const delay = Math.min(30000, 1000 * Math.pow(2, attempt));
      setWebsocketErrorMessage(`${errMsg}. Reconnecting in ${Math.round(delay/1000)}s...`);
      fetchStatusRef.current?.();
      clearHeartbeatTimer();
      if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
        wsRef.current.close();
      }
      if (!shouldReconnectRef.current) {
        return;
      }
      if (targetUrl === websocketDirectUrl && websocketProxyUrl !== websocketDirectUrl) {
        reconnectTimerRef.current = window.setTimeout(() => connect(false), delay);
      } else if (targetUrl !== websocketDirectUrl && websocketDirectUrl) {
        reconnectTimerRef.current = window.setTimeout(() => connect(true), delay);
      } else {
        reconnectTimerRef.current = window.setTimeout(() => connect(false), delay);
      }
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);

        if (msg.type === 'state') {
          const d = msg.data;
          setBotRunning(Boolean(d.running));
          setBotTimeframe(d.timeframe || botTimeframe);
          setBalance(d.balance || d.paper_balance || balance);
          setInitialBalance(typeof d.initial_balance === 'number' ? d.initial_balance : initialBalance);
          setActiveTrades(d.active_trades || {});
          setLatestPrice(d.latest_price || latestPrice);
          setLatestTrend(d.latest_trend || latestTrend);
          setScannedSymbolsStatus(d.scanned_symbols_status || {});
          setScanCount(typeof d.scan_count === 'number' ? d.scan_count : Object.keys(d.scanned_symbols_status || {}).length);
          setScanTotal(typeof d.scan_total === 'number' ? d.scan_total : 0);
          setScanSkipped(typeof d.scan_skipped === 'number' ? d.scan_skipped : 0);
          setSignalsFound(typeof d.signals_found === 'number' ? d.signals_found : 0);
          setOpenTradesCreated(typeof d.open_trades_created === 'number' ? d.open_trades_created : 0);
          setScanCycleCount(typeof d.scan_cycle_count === 'number' ? d.scan_cycle_count : 0);
          if (typeof d.scan_interval_secs === 'number') {
            setScanIntervalSeconds(d.scan_interval_secs);
          }
          if (typeof d.scan_last_broadcast_at === 'number') {
            setScanLastBroadcastAt(d.scan_last_broadcast_at);
          }
          if (typeof d.trading_mode === 'string') {
            setConfig(prev => ({ ...prev, trading_mode: d.trading_mode }));
          }
          if (typeof d.portfolio_margin === 'boolean') {
            setConfig(prev => ({ ...prev, portfolio_margin: d.portfolio_margin }));
          }
          if (typeof d.selected_symbol === 'string') {
            setSelectedSymbol(d.selected_symbol);
          }
          if (typeof d.symbol === 'string') {
            setConfig(prev => ({ ...prev, symbol: d.symbol }));
          }
          if (typeof d.binance_auth_status === 'string') {
            setBinanceAuthStatus(d.binance_auth_status);
          }
          if (typeof d.binance_auth_source === 'string') {
            setBinanceAuthSource(d.binance_auth_source);
          }
          if (typeof d.binance_auth_mode === 'string') {
            setBinanceAuthMode(d.binance_auth_mode);
          }
          if (typeof d.binance_auth_message === 'string') {
            setBinanceAuthMessage(d.binance_auth_message);
          }
          // Prefer explicit scanning flag from backend when provided
          if (typeof d.scanning === 'boolean') {
            setIsScanning(Boolean(d.scanning));
          }
          if (d.trade_history) {
            setTradeHistory(d.trade_history);
          }
        } else if (msg.type === 'log') {
          setLogs(prev => [...prev, msg.data].slice(-100));

          const msgText = msg.data.message || '';
          const lowerMsgText = msgText.toLowerCase();

          const isAuthError = msg.data.level === 'ERROR' ||
            (msg.data.level === 'WARNING' && (
              lowerMsgText.includes('unauthorized') ||
              lowerMsgText.includes('invalid api-key') ||
              lowerMsgText.includes('invalid api-key, ip, or permissions')
            ));

          if (isAuthError) {
            setApiError(msgText);
            showNotification('⚠️ AICryptoSMC API Error', msgText);
          }

          if (msg.data.level === 'INFO' && (
            msgText.includes('OPENED') ||
            msgText.includes('LIQUIDATED') ||
            msgText.includes('Closed position') ||
            msgText.includes('Take Profit') ||
            msgText.includes('Stop Loss')
          )) {
            showNotification('📈 AICryptoSMC Trade Alert', msgText);
          }
        }
      } catch (err) {
        console.warn('[WebSocket] failed to parse message', err, event.data);
      }
    };

    ws.onclose = (event) => {
      clearReconnectTimer();
      clearHeartbeatTimer();
      wsRef.current = null;
      const closedReason = event?.reason ? ` (${event.reason})` : '';
      setWebsocketStatus('closed');
      const wasClean = event?.wasClean === true;
      const code = event?.code || 'unknown';
      const baseMsg = wasClean ? null : `Socket closed unexpectedly (code: ${code})${closedReason}`;
      if (baseMsg) {
        const attempt = (reconnectAttemptRef.current || 0) + 1;
        reconnectAttemptRef.current = attempt;
        const delay = Math.min(30000, 1000 * Math.pow(2, attempt));
        setWebsocketErrorMessage(`${baseMsg}. Reconnecting in ${Math.round(delay/1000)}s...`);
        if (shouldReconnectRef.current) {
          if (targetUrl === websocketDirectUrl && websocketProxyUrl !== websocketDirectUrl) {
            reconnectTimerRef.current = window.setTimeout(() => connect(false), delay);
          } else if (targetUrl !== websocketDirectUrl && websocketDirectUrl) {
            reconnectTimerRef.current = window.setTimeout(() => connect(true), delay);
          } else {
            reconnectTimerRef.current = window.setTimeout(() => connect(false), delay);
          }
        }
      } else {
        setWebsocketErrorMessage(null);
      }
      fetchStatusRef.current?.();
      if (shouldReconnectRef.current) {
        console.debug('[WebSocket] closed', event, 'url=', targetUrl);
        // reconnect already scheduled above for unexpected closes
      }
    };
  }, [clearHeartbeatTimer, clearReconnectTimer, showNotification, websocketProxyUrl, websocketDirectUrl]);

  const scrollToBottom = useCallback(() => {
    if (consoleContainerRef.current) {
      consoleContainerRef.current.scrollTop = consoleContainerRef.current.scrollHeight;
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [logs, scrollToBottom]);

  // Request notification permission on load
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }, []);

  const fetchConfig = useCallback(async () => {
    const data = await safeFetchJson('/config', {}, null);
    if (!data) {
      return;
    }
    setConfig(prev => ({
      ...prev,
      ...data,
      peak_drawdown_exit_pct: typeof data.peak_drawdown_exit_pct === 'number' ? data.peak_drawdown_exit_pct : prev.peak_drawdown_exit_pct,
      max_trade_loss_usd: typeof data.max_trade_loss_usd === 'number' ? data.max_trade_loss_usd : prev.max_trade_loss_usd
    }));
    // Sync backtest parameters with current settings as start
    setBacktestConfig(prev => ({
      ...prev,
      symbol: data.symbol,
      timeframe: data.timeframe,
      risk_pct: data.risk_pct,
      rr_ratio: data.rr_ratio,
      n_swing: data.n_swing,
      x_impulse: data.x_impulse,
      m_range: data.m_range,
      breakeven_trigger: data.breakeven_trigger
    }));
  }, [safeFetchJson]);

  const fetchTrades = useCallback(async () => {
    const data = await safeFetchJson('/trades', {}, null);
    if (!data) {
      return;
    }
    setActiveTrades(data.active_trades || {});
    setTradeHistory(data.trade_history || []);
    setBalance(data.paper_balance);
    if (typeof data.initial_balance === 'number') {
      setInitialBalance(data.initial_balance);
    }
  }, [safeFetchJson]);

  useEffect(() => {
    fetchTradesRef.current = fetchTrades;
  }, [fetchTrades]);

  const fetchStatus = useCallback(async () => {
    const data = await safeFetchJson('/bot/status', {}, null);
    if (!data) {
      return;
    }
    setBotRunning(Boolean(data.running));
    setBotTimeframe(data.timeframe || '15m');
    setBalance(data.balance || data.paper_balance || 0);
    setInitialBalance(typeof data.initial_balance === 'number' ? data.initial_balance : DEFAULT_INITIAL_BALANCE);
    setActiveTrades(data.active_trades || {});
    setLatestPrice(typeof data.latest_price === 'number' ? data.latest_price : 0);
    setLatestTrend(data.latest_trend || 'neutral');
    setScannedSymbolsStatus(data.scanned_symbols_status || {});
    setScanCount(typeof data.scan_count === 'number' ? data.scan_count : Object.keys(data.scanned_symbols_status || {}).length);
    setScanTotal(typeof data.scan_total === 'number' ? data.scan_total : 0);
    setScanSkipped(typeof data.scan_skipped === 'number' ? data.scan_skipped : 0);
    setSignalsFound(typeof data.signals_found === 'number' ? data.signals_found : 0);
    setOpenTradesCreated(typeof data.open_trades_created === 'number' ? data.open_trades_created : 0);
    setScanCycleCount(typeof data.scan_cycle_count === 'number' ? data.scan_cycle_count : 0);
    if (typeof data.scan_interval_secs === 'number') {
      setScanIntervalSeconds(data.scan_interval_secs);
    }
    if (typeof data.scan_last_broadcast_at === 'number') {
      setScanLastBroadcastAt(data.scan_last_broadcast_at);
    }
    if (typeof data.trading_mode === 'string') {
      setConfig(prev => ({ ...prev, trading_mode: data.trading_mode }));
    }
    if (typeof data.portfolio_margin === 'boolean') {
      setConfig(prev => ({ ...prev, portfolio_margin: data.portfolio_margin }));
    }
    if (typeof data.selected_symbol === 'string') {
      setSelectedSymbol(data.selected_symbol);
    }
    if (typeof data.symbol === 'string') {
      setConfig(prev => ({ ...prev, symbol: data.symbol }));
    }
    if (typeof data.binance_auth_status === 'string') {
      setBinanceAuthStatus(data.binance_auth_status);
    }
    if (typeof data.binance_auth_source === 'string') {
      setBinanceAuthSource(data.binance_auth_source);
    }
    if (typeof data.binance_auth_mode === 'string') {
      setBinanceAuthMode(data.binance_auth_mode);
    }
    if (typeof data.binance_auth_message === 'string') {
      setBinanceAuthMessage(data.binance_auth_message);
    }
    if (data.trade_history) {
      setTradeHistory(data.trade_history);
    }
    setStatusLoaded(true);
  }, [safeFetchJson]);

  useEffect(() => {
    fetchStatusRef.current = fetchStatus;
  }, [fetchStatus]);

  const fetchLogs = useCallback(async () => {
    const data = await safeFetchJson('/logs', {}, []);
    if (data) {
      setLogs(data);
    }
  }, [safeFetchJson]);

  useEffect(() => {
    // Force direct backend websocket in local development to avoid proxy edge-cases
    // Prefer the dev-server proxy websocket to avoid cross-origin issues in the browser
    connectWebSocket(false);
    fetchStatus();
    fetchConfig();
    fetchTrades();
    fetchLogs();

    const statusPoll = window.setInterval(() => {
      fetchStatus();
    }, 10000);

    return () => {
      shouldReconnectRef.current = false;
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      window.clearInterval(statusPoll);
    };
  }, [connectWebSocket, fetchConfig, fetchLogs, fetchStatus, fetchTrades]);

  useEffect(() => {
    fetchLiveChart(selectedSymbol);
    const interval = setInterval(() => fetchLiveChart(selectedSymbol), 15000);
    return () => clearInterval(interval);
  }, [selectedSymbol, fetchLiveChart]);

  useEffect(() => {
    const countdown = setInterval(() => {
      const elapsedSeconds = Math.floor((Date.now() - scanLastBroadcastAt) / 1000);
      const remaining = Math.max(scanIntervalSeconds - elapsedSeconds, 0);
      setNextScanCountdown(remaining);
      setIsScanning(botRunning && remaining === 0);
    }, 250);

    return () => clearInterval(countdown);
  }, [scanLastBroadcastAt, scanIntervalSeconds, botRunning]);

  useEffect(() => {
    scrollToBottom();
  }, [logs, scrollToBottom]);

  const saveConfig = async (updatedConfig) => {
    try {
      const res = await fetch('/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatedConfig)
      });
      const data = await res.json();
      setConfig(data);
      if (data.selected_symbol) {
        setSelectedSymbol(data.selected_symbol);
      }
      alert("Settings saved successfully!");
    } catch (e) {
      alert("Failed to save settings: " + e.message);
    }
  };

  const startBot = async () => {
    try {
      await fetch('/bot/start', { method: 'POST' });
      setBotRunning(true);
    } catch (e) {
      console.error(e);
    }
  };

  const stopBot = async () => {
    try {
      await fetch('/bot/stop', { method: 'POST' });
      setBotRunning(false);
    } catch (e) {
      console.error(e);
    }
  };

  const handleSelectSymbol = async (symbol) => {
    setSelectedSymbol(symbol);
    try {
      await fetch('/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selected_symbol: symbol })
      });
      fetchLiveChart(symbol);
    } catch (e) {
      console.error("Failed to update selected symbol config", e);
    }
  };

  const runBacktestExecution = async () => {
    setBacktesting(true);
    setBacktestResults(null);
    try {
      const res = await fetch('/backtest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(backtestConfig)
      });
      if (res.ok) {
        const data = await res.json();
        setBacktestResults(data);
      } else {
        const err = await res.json();
        alert("Backtest failed: " + err.detail);
      }
    } catch (e) {
      alert("Backtest error: " + e.message);
    } finally {
      setBacktesting(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {/* Header bar */}
      <header style={styles.header}>
        <div style={styles.brand}>
          <Cpu size={24} style={{ color: 'var(--accent-purple)' }} />
          <h1 style={styles.title}>AICrypto<span style={{ color: 'var(--accent-purple)' }}>SMC</span></h1>
          <span style={styles.tagline}>Smart Money Concepts Automated Trading</span>
        </div>
        
        <div style={styles.nav}>
          <button 
            style={{ ...styles.navBtn, ...(activeTab === 'live' ? styles.navActive : {}) }}
            onClick={() => { setActiveTab('live'); fetchTrades(); }}
          >
            <Activity size={16} /> Live Dashboard
          </button>
          <button 
            style={{ ...styles.navBtn, ...(activeTab === 'history' ? styles.navActive : {}) }}
            onClick={() => { setActiveTab('history'); fetchTrades(); }}
          >
            <History size={16} /> Trading History
          </button>
          <button 
            style={{ ...styles.navBtn, ...(activeTab === 'backtest' ? styles.navActive : {}) }}
            onClick={() => setActiveTab('backtest')}
          >
            <BarChart3 size={16} /> Historical Backtester
          </button>
        </div>
      </header>

      {/* Critical API Error Banner */}
      {apiError && (
        <div style={{
          background: 'rgba(239, 68, 68, 0.2)',
          borderBottom: '1px solid rgba(239, 68, 68, 0.4)',
          padding: '12px 40px',
          color: '#fca5a5',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          fontSize: '0.9rem',
          backdropFilter: 'blur(10px)',
          animation: 'fadeIn 0.3s ease'
        }}>
          <ShieldAlert size={18} style={{ color: 'var(--bearish)' }} />
          <div style={{ flexGrow: 1 }}>
            <strong>Critical API Connection Failure:</strong> {apiError}. The bot is unable to query your balance or submit trades. Please check your API credentials or whitelisted IP settings on Binance.
          </div>
          <button 
            onClick={() => setApiError(null)} 
            style={{
              background: 'rgba(255, 255, 255, 0.1)',
              border: 'none',
              borderRadius: '4px',
              padding: '4px 8px',
              color: 'white',
              fontSize: '0.8rem',
              cursor: 'pointer',
              transition: 'background 0.2s'
            }}
            onMouseOver={e => e.target.style.background = 'rgba(255, 255, 255, 0.2)'}
            onMouseOut={e => e.target.style.background = 'rgba(255, 255, 255, 0.1)'}
          >
            Dismiss
          </button>
        </div>
      )}

      {activeTab === 'live' && (
        <div style={styles.scanStatusBarTop}>
          <div style={styles.scanStatusItem}>
            <span style={styles.scanStatusLabel}>Scan Progress ({scanCycleCount})</span>
            <span style={styles.scanStatusValue}>{scanCount} / {scanTotal}</span>
            <div style={styles.scanProgressTrack}>
              <div style={{ ...styles.scanProgressFill, width: `${Math.round((scanCount / (scanTotal || 1)) * 100)}%` }} />
            </div>
            {scanSkipped > 0 && (
              <span style={styles.scanSkippedLabel}>{scanSkipped} skipped</span>
            )}
          </div>
          <div style={styles.scanStatusItem}>
            <span style={styles.scanStatusLabel}>Active Positions</span>
            <span style={styles.scanStatusValue}>{Object.keys(activeTrades).length}</span>
          </div>
          <div style={styles.scanStatusItem}>
            <span style={styles.scanStatusLabel}>Signals Found</span>
            <span style={styles.scanStatusValue}>{signalsFound}</span>
          </div>
          <div style={styles.scanStatusItem}>
            <span style={styles.scanStatusLabel}>Trades Opened</span>
            <span style={styles.scanStatusValue}>{openTradesCreated}</span>
          </div>
          <div style={styles.scanStatusItem}>
            <span style={styles.scanStatusLabel}>Next Scan In</span>
            <span style={styles.scanStatusValue}>
              {!botRunning
                ? 'Idle'
                : scanTotal === 0
                  ? 'Waiting...'
                  : nextScanCountdown === 0
                    ? 'Scanning...'
                    : `${nextScanCountdown} sec`}
            </span>
          </div>
          <div style={styles.scanStatusItem}>
            <span style={styles.scanStatusLabel}>Connection</span>
            <span style={{
              ...styles.scanStatusValue,
              color: websocketStatus === 'open' ? 'var(--bullish)' : websocketStatus === 'connecting' ? 'var(--accent-teal)' : 'var(--bearish)'
            }}>
              {websocketStatus === 'open'
                ? 'Connected'
                : websocketStatus === 'connecting'
                ? 'Connecting'
                : websocketStatus === 'error'
                ? 'Error'
                : websocketStatus === 'closed'
                ? 'Closed'
                : 'Disconnected'}
            </span>
            <span style={styles.scanStatusSecondary}>{websocketUrl}</span>
            {(websocketErrorMessage && websocketStatus !== 'open') && (
              <div style={{ ...styles.scanStatusSecondary, color: 'var(--bearish)', marginTop: '4px' }}>
                {websocketErrorMessage}
              </div>
            )}
            {websocketStatus !== 'open' && (
              <button
                type="button"
                onClick={() => {
                  shouldReconnectRef.current = true;
                  connectWebSocket();
                }}
                style={{
                  marginTop: '8px',
                  padding: '6px 10px',
                  borderRadius: '10px',
                  border: '1px solid rgba(148, 163, 184, 0.24)',
                  background: 'rgba(255,255,255,0.04)',
                  color: 'var(--text-main)',
                  cursor: 'pointer',
                  fontSize: '0.75rem'
                }}
              >
                Reconnect
              </button>
            )}
          </div>
          <div style={styles.scanStatusItem}>
            <span style={styles.scanStatusLabel}>Binance Auth</span>
            <span style={{
              ...styles.scanStatusValue,
              color: binanceAuthStatus === 'success' ? 'var(--bullish)' : binanceAuthStatus === 'pending' || binanceAuthStatus === 'unknown' ? 'var(--accent-teal)' : 'var(--bearish)'
            }}>
              {binanceAuthStatus === 'success'
                ? `OK (${binanceAuthMode || 'auth'})`
                : binanceAuthStatus === 'pending'
                ? 'Pending'
                : binanceAuthStatus === 'unknown'
                ? 'Unknown'
                : 'Failed'
              }
            </span>
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <main style={styles.mainContent}>
        {activeTab === 'live' ? (
          /* LIVE TRADING TAB */
          <>
            <div style={styles.dashboardGrid}>
            
            {/* Column 1: Scanned Coins Sidebar */}
            <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '15px', maxHeight: 'calc(100vh - 120px)', overflowY: 'auto' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', borderBottom: '1px solid var(--border-color)', paddingBottom: '10px' }}>
                <Cpu size={18} style={{ color: 'var(--accent-purple)' }} />
                <h3 style={styles.cardTitle}>Scanned Markets</h3>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {Object.keys(scannedSymbolsStatus).length > 0 ? (
                  Object.entries(scannedSymbolsStatus).map(([sym, status]) => {
                    const isSelected = sym === selectedSymbol;
                    const trendColor = status.trend === 'uptrend' ? 'var(--bullish)' : status.trend === 'downtrend' ? 'var(--bearish)' : 'var(--text-muted)';
                    return (
                      <div 
                        key={sym} 
                        onClick={() => handleSelectSymbol(sym)}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '10px 12px',
                          borderRadius: '8px',
                          cursor: 'pointer',
                          border: isSelected ? '1px solid var(--accent-purple)' : '1px solid transparent',
                          background: isSelected ? 'rgba(168, 85, 247, 0.08)' : 'rgba(255, 255, 255, 0.02)',
                          transition: 'all 0.2s',
                        }}
                        className="coin-row-hover"
                      >
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span style={{ fontWeight: '700', fontSize: '0.85rem', color: isSelected ? 'var(--text-main)' : 'var(--text-muted)' }}>
                              {sym.replace('USDT', '')}
                            </span>
                            {status.has_active_trade && (
                              <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--accent-teal)', boxShadow: '0 0 6px var(--accent-teal)' }} />
                            )}
                          </div>
                          <span style={{ fontSize: '0.7rem', color: trendColor, textTransform: 'uppercase', fontWeight: '600' }}>
                            {status.trend}
                          </span>
                        </div>
                        <span style={{ fontSize: '0.85rem', fontWeight: '700', color: 'var(--text-main)' }}>
                           ${status.price.toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 4 })}
                        </span>
                      </div>
                    );
                  })
                ) : (
                  <div style={{ textAlign: 'center', color: 'var(--text-dark)', fontSize: '0.8rem', padding: '20px 0' }}>
                    No scanned markets active. Start the bot.
                  </div>
                )}
              </div>
            </div>
            
            {/* Column 2: Status & Config */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              
              {/* Bot Control Card */}
              <div className="glass-card" style={botRunning ? { ...styles.controlCard, ...styles.activeGlow } : styles.controlCard}>
                <div style={styles.cardHeader}>
                  <h3>Trading Bot Controller</h3>
                  <span style={{ 
                    ...styles.statusDot, 
                    backgroundColor: botRunning ? 'var(--bullish)' : 'var(--text-dark)',
                    boxShadow: botRunning ? '0 0 10px var(--bullish)' : 'none'
                  }} />
                </div>

                <div style={styles.statusRow}>
                  <div style={styles.statusCell}>
                    <span style={styles.statusLabel}>Pair</span>
                    <span style={styles.statusValue}>{selectedSymbol}</span>
                  </div>
                  <div style={styles.statusCell}>
                    <span style={styles.statusLabel}>Timeframe</span>
                    <span style={styles.statusValue}>{botTimeframe}</span>
                  </div>
                  <div style={styles.statusCell}>
                    <span style={styles.statusLabel}>SMC Bias</span>
                    <span style={{ 
                      ...styles.statusValue, 
                      color: latestTrend === 'uptrend' ? 'var(--bullish)' : latestTrend === 'downtrend' ? 'var(--bearish)' : 'var(--text-muted)' 
                    }}>
                      {(latestTrend || 'neutral').toUpperCase()}
                    </span>
                  </div>
                </div>

                <div style={styles.statusRow}>
                  <div style={styles.statusCell}>
                    <span style={styles.statusLabel}>Latest Price</span>
                     <span style={styles.statusValue}>${latestPrice ? latestPrice.toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 4 }) : '---'}</span>
                  </div>
                  <div style={styles.statusCell}>
                    <span style={styles.statusLabel}>
                      {config.trading_mode === 'live' ? 'Binance Balance' : 'Paper Balance'}
                    </span>
                    <span style={{ ...styles.statusValue, color: 'var(--accent-teal)' }}>
                      ${balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                  </div>
                </div>
                <div style={styles.statusRow}>
                  <div style={styles.statusCell}>
                    <span style={styles.statusLabel}>Total P&L</span>
                    <span style={{
                      ...styles.statusValue,
                      color: totalPnl > 0 ? 'var(--bullish)' : totalPnl < 0 ? 'var(--bearish)' : 'var(--text-muted)'
                    }}>
                      ${formattedTotalPnl} <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>({formattedTotalPnlPct})</span>
                    </span>
                  </div>
                </div>
                <div style={styles.statusRow}>
                  <div style={styles.statusCell}>
                    <span style={styles.statusLabel}>Binance Auth</span>
                    <span style={{
                      ...styles.statusValue,
                      color: binanceAuthStatus === 'success' ? 'var(--bullish)' : binanceAuthStatus === 'pending' ? 'var(--accent-teal)' : 'var(--bearish)'
                    }}>
                      {binanceAuthStatus === 'success'
                        ? `OK (${binanceAuthMode || 'auth'})`
                        : binanceAuthStatus === 'pending'
                        ? 'Pending'
                        : 'Failed'}
                    </span>
                  </div>
                  <div style={styles.statusCell}>
                    <span style={styles.statusLabel}>Auth Source</span>
                    <span style={styles.statusValue}>{binanceAuthSource || 'unknown'}</span>
                  </div>
                </div>
              </div>

              {/* Active Position Card */}
              <div className="glass-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
                  <h3 style={{ ...styles.cardTitle, margin: 0 }}>Active SMC Positions</h3>
                  {Object.keys(activeTrades).length > 0 && (
                    <button 
                      onClick={async () => {
                        if (window.confirm("Are you sure you want to liquidate all active positions at their current market prices?")) {
                          try {
                            const res = await fetch('/trades/liquidate', { method: 'POST' });
                            const data = await res.json();
                            setActiveTrades(data.active_trades || {});
                            setTradeHistory(data.trade_history || []);
                            setBalance(data.paper_balance || DEFAULT_INITIAL_BALANCE);
                            alert("All active positions liquidated successfully.");
                          } catch (e) {
                            alert("Failed to liquidate positions: " + e.message);
                          }
                        }
                      }} 
                      className="btn-danger" 
                      style={{ padding: '6px 12px', fontSize: '0.8rem', borderRadius: '6px' }}
                    >
                      Liquidate All
                    </button>
                  )}
                </div>
                {Object.keys(activeTrades).length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
                    {Object.entries(activeTrades).map(([symbol, trade]) => {
                      const markPrice = parseFloat(trade.mark_price) || 0;
                      const currentPriceForSymbol = markPrice > 0
                        ? markPrice
                        : symbol === selectedSymbol
                          ? (latestPrice || scannedSymbolsStatus[symbol]?.price || trade.entry_price)
                          : (scannedSymbolsStatus[symbol]?.price || trade.entry_price);
                      
                      const entryPrice = parseFloat(trade.entry_price) || 0;
                      const size = parseFloat(trade.size) || 0;
                      const pnl = trade.type === 'long' 
                        ? (currentPriceForSymbol - entryPrice) * size
                        : (entryPrice - currentPriceForSymbol) * size;
                      const pnlPct = (pnl / (trade.entry_price * trade.size)) * 100;
                      const positionValue = trade.entry_price * trade.size;
                      
                      return (
                        <div key={symbol} style={{ border: '1px solid var(--border-color)', borderRadius: '8px', padding: '12px', background: 'rgba(255, 255, 255, 0.02)' }}>
                          <div style={styles.positionHeader}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <span style={{ fontWeight: 'bold', color: 'var(--text-main)' }}>{symbol}</span>
                              <span className={`badge ${trade.type === 'long' ? 'badge-bullish' : 'badge-bearish'}`}>
                                {trade.type.toUpperCase()}
                              </span>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                              <span style={styles.entryTime}>
                                {new Date(trade.entry_time).toLocaleTimeString()}
                              </span>
                              <button
                                onClick={async (e) => {
                                  e.stopPropagation();
                                  if (window.confirm(`Are you sure you want to liquidate the ${symbol} position?`)) {
                                    try {
                                      const res = await fetch(`/trades/liquidate?symbol=${symbol}`, { method: 'POST' });
                                      const data = await res.json();
                                      setActiveTrades(data.active_trades || {});
                                      setTradeHistory(data.trade_history || []);
                                      setBalance(data.paper_balance || DEFAULT_INITIAL_BALANCE);
                                      alert(`${symbol} position liquidated successfully.`);
                                    } catch (err) {
                                      alert("Failed to liquidate position: " + err.message);
                                    }
                                  }
                                }}
                                className="btn-danger"
                                style={{ 
                                  padding: '2px 8px', 
                                  fontSize: '0.75rem', 
                                  borderRadius: '4px',
                                  cursor: 'pointer'
                                }}
                              >
                                Liquidate
                              </button>
                            </div>
                          </div>

                          <div style={{ ...styles.metricGrid, marginTop: '10px' }}>
                            <div>
                              <span style={styles.metricLabel}>Entry</span>
                              <span style={styles.metricValue}>${formatPrice(trade.entry_price)}</span>
                            </div>
                            <div>
                              <span style={styles.metricLabel}>Current</span>
                              <span style={styles.metricValue}>${formatPrice(currentPriceForSymbol)}</span>
                            </div>
                            <div>
                              <span style={styles.metricLabel}>SL</span>
                              <span style={{ ...styles.metricValue, color: 'var(--bearish)' }}>${formatPrice(trade.sl)}</span>
                            </div>
                            <div>
                              <span style={styles.metricLabel}>TP</span>
                              <span style={{ ...styles.metricValue, color: 'var(--bullish)' }}>${formatPrice(trade.tp)}</span>
                            </div>
                            <div>
                              <span style={styles.metricLabel}>Size</span>
                              <span style={styles.metricValue}>{Number(trade.size).toLocaleString(undefined, { maximumFractionDigits: 6 })} {symbol.replace('USDT', '')}</span>
                            </div>
                            <div>
                              <span style={styles.metricLabel}>Exposure</span>
                              <span style={styles.metricValue}>${formatPrice(positionValue)}</span>
                            </div>
                            <div>
                              <span style={styles.metricLabel}>Risk</span>
                              <span style={styles.metricValue}>${trade.risk_amount !== undefined && trade.risk_amount !== null ? Number(trade.risk_amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '---'}</span>
                            </div>
                          </div>

                          <div style={{
                            ...styles.floatingPnl,
                            marginTop: '10px',
                            background: pnl >= 0 ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)',
                            borderColor: pnl >= 0 ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                          }}>
                            <span style={styles.pnlLabel}>Unrealized PnL</span>
                            <span style={{
                              ...styles.pnlValue,
                              color: pnl >= 0 ? 'var(--bullish)' : 'var(--bearish)'
                            }}>
                              {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)} ({pnl >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%)
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div style={styles.emptyState}>
                    <AlertCircle size={24} style={{ color: 'var(--text-dark)' }} />
                    <p style={{ color: 'var(--text-muted)' }}>No active trades currently. Waiting for SMC zone sweeps...</p>
                  </div>
                )}
              </div>

              {/* Completed SMC Trades Card */}
              <div className="glass-card">
                <h3 style={styles.cardTitle}>Completed SMC Trades</h3>
                {tradeHistory && tradeHistory.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '15px', maxHeight: '300px', overflowY: 'auto', paddingRight: '5px' }}>
                    {[...tradeHistory].reverse().map((trade, idx) => {
                      const isProfit = trade.pnl > 0;
                      const isLoss = trade.pnl < 0;
                      const badgeClass = trade.status === 'TP' ? 'badge-bullish' : trade.status === 'SL' ? 'badge-bearish' : 'badge-neutral';
                      
                      return (
                        <div key={idx} style={{ border: '1px solid var(--border-color)', borderRadius: '8px', padding: '10px', background: 'rgba(255, 255, 255, 0.01)', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                          <div style={styles.positionHeader}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <span style={{ fontWeight: 'bold', color: 'var(--text-main)', fontSize: '0.9rem' }}>{trade.symbol}</span>
                              <span className={`badge ${trade.type === 'long' ? 'badge-bullish' : 'badge-bearish'}`} style={{ fontSize: '0.65rem', padding: '2px 6px' }}>
                                {trade.type.toUpperCase()}
                              </span>
                              <span className={`badge ${badgeClass}`} style={{ fontSize: '0.65rem', padding: '2px 6px' }}>
                                {trade.status}
                              </span>
                            </div>
                            <span style={{ ...styles.entryTime, fontSize: '0.75rem' }}>
                              {new Date(trade.exit_time).toLocaleTimeString()}
                            </span>
                          </div>
                          
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                            <span>Entry: ${trade.entry_price.toLocaleString(undefined, {minimumFractionDigits: 4, maximumFractionDigits: 4})}</span>
                            <span>Exit: ${trade.exit_price.toLocaleString(undefined, {minimumFractionDigits: 4, maximumFractionDigits: 4})}</span>
                            <span style={{ fontWeight: 'bold', color: isProfit ? 'var(--bullish)' : isLoss ? 'var(--bearish)' : 'var(--text-muted)' }}>
                              {trade.pnl > 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div style={styles.emptyState}>
                    <AlertCircle size={24} style={{ color: 'var(--text-dark)' }} />
                    <p style={{ color: 'var(--text-muted)' }}>No completed trades yet.</p>
                  </div>
                )}
              </div>

              {/* Bot Settings */}
              <SettingsPanel config={config} saveConfig={saveConfig} />

            </div>

            {/* Column 3: Chart & Logs */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              
              {/* Chart Display */}
              <div className="glass-card" style={{ flexGrow: 1, minHeight: '400px', display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
                  <h3 style={styles.cardTitle}>Live Price Chart</h3>
                  <div style={{ display: 'flex', gap: '8px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    <span>⚡ Real-time Updates</span>
                  </div>
                </div>
                
                {/* Visualizer component */}
                <div style={{ flexGrow: 1, position: 'relative', minHeight: '380px' }}>
                  {liveChartData && liveChartData.length > 0 ? (
                    <SMCChart 
                      data={liveChartData} 
                      structures={liveStructures} 
                      symbol={selectedSymbol} 
                      timeframe={botTimeframe} 
                      activeTrade={activeTrades[selectedSymbol]}
                    />
                  ) : (
                    <div style={styles.chartFallback}>
                      <RefreshCw size={24} style={{ animation: 'spin 2s linear infinite', color: 'var(--accent-purple)' }} />
                      <p style={{ marginTop: '10px' }}>Loading chart data...</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Real-time Logs Console */}
              <div className="glass-card" style={styles.consoleCard}>
                <div style={styles.consoleHeader}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Activity size={16} style={{ color: 'var(--accent-purple)' }} />
                    <h3 style={styles.cardTitle}>Live Monitoring Logs</h3>
                  </div>
                  <button onClick={fetchLogs} style={styles.refreshBtn}><RefreshCw size={12} /></button>
                </div>
                
                <div ref={consoleContainerRef} style={styles.consoleContent}>
                  {logs.map((log, idx) => (
                    <div key={idx} style={styles.logRow}>
                      <span style={styles.logTime}>
                        {log.time 
                          ? (typeof log.time === 'string' && log.time.includes(" ") 
                             ? log.time.split(" ")[1] 
                             : new Date(log.time).toLocaleTimeString()) 
                          : ''}
                      </span>
                      <span style={{ 
                        ...styles.logLevel, 
                        color: log.level === 'ERROR' ? 'var(--bearish)' : log.level === 'WARNING' ? 'var(--accent-purple)' : 'var(--accent-teal)'
                      }}>[{log.level}]</span>
                      <span style={styles.logMsg}>{log.message}</span>
                    </div>
                  ))}
                  <div ref={logsEndRef} />
                </div>
              </div>

            </div>

          </div>
          </>
        ) : activeTab === 'history' ? (
          /* TRADING HISTORY TAB */
          <TradingHistoryView 
            tradeHistory={tradeHistory} 
            balance={balance}
            onResetHistory={async () => {
              if (window.confirm(`Are you sure you want to reset your trading history? This will clear all completed trades and reset the paper balance to $${DEFAULT_INITIAL_BALANCE.toLocaleString(undefined, {minimumFractionDigits: 1})}.`)) {
                try {
                  const res = await fetch('/trades/reset', { method: 'POST' });
                  const data = await res.json();
                  setTradeHistory(data.trade_history || []);
                  setBalance(data.paper_balance || DEFAULT_INITIAL_BALANCE);
                  alert("Session history and balance reset successfully.");
                } catch (e) {
                  alert("Failed to reset history: " + e.message);
                }
              }
            }}
          />
        ) : (
          /* HISTORICAL BACKTEST TAB */
          <div style={styles.backtestContainer}>
            
            {/* Configurations & Actions */}
            <div className="glass-card" style={styles.backtestConfigCard}>
              <h3 style={{ ...styles.cardTitle, marginBottom: '20px' }}>Backtest Parameters</h3>
              
              <div style={styles.backtestFormGrid}>
                <div className="form-group">
                  <label>Asset Symbol</label>
                  <select 
                    value={backtestConfig.symbol} 
                    className="form-select"
                    onChange={e => setBacktestConfig(prev => ({ ...prev, symbol: e.target.value }))}
                  >
                    {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>

                <div className="form-group">
                  <label>Candle Timeframe</label>
                  <select 
                    value={backtestConfig.timeframe} 
                    className="form-select"
                    onChange={e => setBacktestConfig(prev => ({ ...prev, timeframe: e.target.value }))}
                  >
                    {TIMEFRAMES.map(tf => <option key={tf} value={tf}>{tf}</option>)}
                  </select>
                </div>

                <div className="form-group">
                  <label>Historical Candles Count</label>
                  <input 
                    type="number" 
                    value={backtestConfig.limit} 
                    className="form-input"
                    onChange={e => setBacktestConfig(prev => ({ ...prev, limit: parseInt(e.target.value) || 200 }))}
                  />
                </div>

                <div className="form-group">
                  <label>Starting Balance (USD)</label>
                  <input 
                    type="number" 
                    value={backtestConfig.initial_balance} 
                    className="form-input"
                    onChange={e => setBacktestConfig(prev => ({ ...prev, initial_balance: parseFloat(e.target.value) || DEFAULT_INITIAL_BALANCE }))}
                  />
                </div>

                <div className="form-group">
                  <label>Risk Per Trade (%)</label>
                  <input 
                    type="number" 
                    step="0.1" 
                    value={backtestConfig.risk_pct} 
                    className="form-input"
                    onChange={e => setBacktestConfig(prev => ({ ...prev, risk_pct: parseFloat(e.target.value) || 1 }))}
                  />
                </div>

                <div className="form-group">
                  <label>Risk Reward Ratio (R)</label>
                  <input 
                    type="number" 
                    step="0.5" 
                    value={backtestConfig.rr_ratio} 
                    className="form-input"
                    onChange={e => setBacktestConfig(prev => ({ ...prev, rr_ratio: parseFloat(e.target.value) || 2 }))}
                  />
                </div>

                <div className="form-group">
                  <label>Swing Lookback (N)</label>
                  <input 
                    type="number" 
                    value={backtestConfig.n_swing} 
                    className="form-input"
                    onChange={e => setBacktestConfig(prev => ({ ...prev, n_swing: parseInt(e.target.value) || 2 }))}
                  />
                </div>

                <div className="form-group">
                  <label>Impulse Multiplier (X)</label>
                  <input 
                    type="number" 
                    step="0.1" 
                    value={backtestConfig.x_impulse} 
                    className="form-input"
                    onChange={e => setBacktestConfig(prev => ({ ...prev, x_impulse: parseFloat(e.target.value) || 2.0 }))}
                  />
                </div>
              </div>

              <div style={{ marginTop: '20px' }}>
                <button 
                  onClick={runBacktestExecution} 
                  className="btn-primary" 
                  disabled={backtesting}
                  style={{ width: '100%', justifyContent: 'center' }}
                >
                  {backtesting ? (
                    <>
                      <RefreshCw size={18} style={{ animation: 'spin 2s linear infinite' }} /> Processing Backtest Simulation...
                    </>
                  ) : (
                    <>
                      <BarChart3 size={18} /> Run Backtest Simulation
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Backtest Results Display */}
            {backtestResults && (
              <div style={styles.backtestResultsArea}>
                
                {/* Stats Summary Cards */}
                <div style={styles.statsSummaryGrid}>
                  
                  <div className="glass-card" style={styles.statCard}>
                    <TrendingUp size={24} style={{ color: 'var(--accent-purple)' }} />
                    <div>
                      <span style={styles.statLabel}>Net Profit</span>
                      <h4 style={{ 
                        ...styles.statVal, 
                        color: backtestResults.summary.net_profit >= 0 ? 'var(--bullish)' : 'var(--bearish)'
                      }}>
                        {backtestResults.summary.net_profit >= 0 ? '+' : ''}
                        ${backtestResults.summary.net_profit.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                        <span style={styles.smallPct}> ({backtestResults.summary.return_pct.toFixed(2)}%)</span>
                      </h4>
                    </div>
                  </div>

                  <div className="glass-card" style={styles.statCard}>
                    <Activity size={24} style={{ color: 'var(--accent-teal)' }} />
                    <div>
                      <span style={styles.statLabel}>Total Trades</span>
                      <h4 style={styles.statVal}>{backtestResults.summary.total_trades}</h4>
                    </div>
                  </div>

                  <div className="glass-card" style={styles.statCard}>
                    <CheckCircle2 size={24} style={{ color: 'var(--bullish)' }} />
                    <div>
                      <span style={styles.statLabel}>Win Rate</span>
                      <h4 style={styles.statVal}>{backtestResults.summary.win_rate.toFixed(1)}%</h4>
                    </div>
                  </div>

                  <div className="glass-card" style={styles.statCard}>
                    <DollarSign size={24} style={{ color: 'var(--accent-blue)' }} />
                    <div>
                      <span style={styles.statLabel}>Profit Factor</span>
                      <h4 style={styles.statVal}>{backtestResults.summary.profit_factor.toFixed(2)}</h4>
                    </div>
                  </div>

                 </div>

                {/* Backtest Chart Display */}
                <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '15px', marginTop: '20px', marginBottom: '20px' }}>
                  <h3 style={styles.cardTitle}>SMC Backtest Visualizer ({backtestConfig.symbol} - {backtestConfig.timeframe})</h3>
                  <div style={{ position: 'relative', minHeight: '380px' }}>
                    {backtestResults.chart_data && backtestResults.chart_data.length > 0 ? (
                      <SMCChart 
                        data={backtestResults.chart_data} 
                        structures={backtestResults.structures} 
                        symbol={backtestConfig.symbol} 
                        timeframe={backtestConfig.timeframe} 
                      />
                    ) : (
                      <div style={styles.chartFallback}>No chart data returned from backtest.</div>
                    )}
                  </div>
                </div>

                {/* Backtest Trades Table */}
                <div className="glass-card">
                  <h3 style={{ ...styles.cardTitle, marginBottom: '15px' }}>Trades Executed</h3>
                  {backtestResults.trades.length > 0 ? (
                    <div style={styles.tableWrapper}>
                      <table style={styles.table}>
                        <thead>
                          <tr style={styles.tr}>
                            <th style={styles.th}>Type</th>
                            <th style={styles.th}>Entry Price</th>
                            <th style={styles.th}>Exit Price</th>
                            <th style={styles.th}>Stop Loss</th>
                            <th style={styles.th}>Take Profit</th>
                            <th style={styles.th}>Net PnL</th>
                            <th style={styles.th}>Result</th>
                          </tr>
                        </thead>
                        <tbody>
                          {backtestResults.trades.map((trade, idx) => (
                            <tr key={idx} style={styles.tr}>
                              <td style={styles.td}>
                                <span className={`badge ${trade.type === 'long' ? 'badge-bullish' : 'badge-bearish'}`}>
                                  {trade.type.toUpperCase()}
                                </span>
                              </td>
                              <td style={styles.td}>{`$${formatPrice(trade.entry_price)}`}</td>
                              <td style={styles.td}>{`$${formatPrice(trade.exit_price)}`}</td>
                              <td style={styles.td}>{`$${formatPrice(trade.sl)}`}</td>
                              <td style={styles.td}>{`$${formatPrice(trade.tp)}`}</td>
                              <td style={{ 
                                ...styles.td, 
                                color: trade.pnl >= 0 ? 'var(--bullish)' : 'var(--bearish)',
                                fontWeight: '600'
                              }}>
                                {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                              </td>
                              <td style={styles.td}>
                                <span style={{
                                  color: trade.status === 'TP' ? 'var(--bullish)' : trade.status === 'SL' ? 'var(--bearish)' : 'var(--text-muted)'
                                }}>{trade.status}</span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div style={styles.emptyState}>
                      <AlertCircle size={24} style={{ color: 'var(--text-dark)' }} />
                      <p>No trades executed in this backtesting timeframe. Try adjusting your timeframe or parameters.</p>
                    </div>
                  )}
                </div>

              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

function formatDuration(entryTime, exitTime) {
  if (!entryTime || !exitTime) return '---';
  const diffMs = exitTime - entryTime;
  if (diffMs <= 0) return '0s';
  const diffSec = Math.floor(diffMs / 1000);
  const hrs = Math.floor(diffSec / 3600);
  const mins = Math.floor((diffSec % 3600) / 60);
  const secs = diffSec % 60;
  
  if (hrs > 0) {
    return `${hrs}h ${mins}m`;
  }
  if (mins > 0) {
    return `${mins}m ${secs}s`;
  }
  return `${secs}s`;
}

function formatTimestamp(ts) {
  if (!ts) return '---';
  const d = new Date(ts);
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
}

function formatPrice(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) {
    return '---';
  }

  const price = Number(value);
  const absPrice = Math.abs(price);

  let digits = 4;
  if (absPrice === 0) {
    digits = 8;
  } else if (absPrice < 0.0001) {
    digits = 10;
  } else if (absPrice < 0.001) {
    digits = 9;
  } else if (absPrice < 0.01) {
    digits = 8;
  } else if (absPrice < 0.1) {
    digits = 7;
  } else if (absPrice < 1) {
    digits = 6;
  } else if (absPrice < 10) {
    digits = 5;
  } else {
    digits = 4;
  }

  return price.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function TradingHistoryView({ tradeHistory, balance, onResetHistory }) {
  const [symbolFilter, setSymbolFilter] = useState('ALL');
  const [typeFilter, setTypeFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [sortBy, setSortBy] = useState('newest'); // 'newest' | 'oldest' | 'pnl_desc' | 'pnl_asc'
  
  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  // Extract unique symbols from history
  const uniqueSymbols = ['ALL', ...new Set(tradeHistory.map(t => t.symbol))];

  // Calculate statistics
  const totalTrades = tradeHistory.length;
  const wins = tradeHistory.filter(t => t.pnl > 0).length;
  const losses = tradeHistory.filter(t => t.pnl < 0).length;
  const breakEvens = tradeHistory.filter(t => t.pnl === 0).length;
  
  const winRate = totalTrades > 0 ? (wins / totalTrades) * 100 : 0;
  
  const grossProfits = tradeHistory.filter(t => t.pnl > 0).reduce((sum, t) => sum + t.pnl, 0);
  const grossLosses = tradeHistory.filter(t => t.pnl < 0).reduce((sum, t) => sum + t.pnl, 0);
  const netPnL = tradeHistory.reduce((sum, t) => sum + t.pnl, 0);
  const avgPnL = totalTrades > 0 ? netPnL / totalTrades : 0;
  
  const profitFactor = Math.abs(grossLosses) > 0 ? grossProfits / Math.abs(grossLosses) : grossProfits;
  
  const maxWin = tradeHistory.length > 0 ? Math.max(...tradeHistory.map(t => t.pnl)) : 0;
  const maxLoss = tradeHistory.length > 0 ? Math.min(...tradeHistory.map(t => t.pnl)) : 0;

  // Filter trade history
  const filteredTrades = tradeHistory.filter(trade => {
    if (symbolFilter !== 'ALL' && trade.symbol !== symbolFilter) return false;
    if (typeFilter !== 'ALL' && trade.type !== typeFilter) return false;
    if (statusFilter !== 'ALL' && trade.status !== statusFilter) return false;
    return true;
  });

  // Sort trade history
  const sortedTrades = [...filteredTrades].sort((a, b) => {
    if (sortBy === 'newest') {
      return (b.exit_time || 0) - (a.exit_time || 0);
    }
    if (sortBy === 'oldest') {
      return (a.exit_time || 0) - (b.exit_time || 0);
    }
    if (sortBy === 'pnl_desc') {
      return b.pnl - a.pnl;
    }
    if (sortBy === 'pnl_asc') {
      return a.pnl - b.pnl;
    }
    return 0;
  });

  // Paginated trades
  const totalPages = Math.ceil(sortedTrades.length / itemsPerPage);
  const paginatedTrades = sortedTrades.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

  // Reset page when filter changes
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCurrentPage(1);
  }, [symbolFilter, typeFilter, statusFilter, sortBy]);

  // Styling helper for Profit Factor
  let pfColor = 'var(--text-muted)';
  let pfLabel = 'Neutral';
  if (totalTrades > 0) {
    if (profitFactor >= 1.5) {
      pfColor = 'var(--accent-teal)';
      pfLabel = 'Excellent';
    } else if (profitFactor >= 1.0) {
      pfColor = 'var(--accent-blue)';
      pfLabel = 'Good';
    } else if (profitFactor > 0) {
      pfColor = 'var(--bearish)';
      pfLabel = 'Unprofitable';
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      
      {/* 1. Header with Title & Reset Button */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: '800', color: 'var(--text-main)' }}>Trade Performance Analyzer</h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Analyze and track all automated SMC trades completed in this session.</p>
        </div>
        <button onClick={onResetHistory} className="btn-danger">
          <History size={16} /> Reset Session Data
        </button>
      </div>

      {/* 2. Stats Grid */}
      <div style={styles.statsSummaryGrid}>
        
        {/* Net Profit Card */}
        <div className="glass-card" style={styles.statCard}>
          <TrendingUp size={28} style={{ color: netPnL >= 0 ? 'var(--bullish)' : 'var(--bearish)' }} />
          <div style={{ flexGrow: 1 }}>
            <span style={styles.statLabel}>Net Profit/Loss</span>
            <h4 style={{ 
              ...styles.statVal, 
              color: netPnL >= 0 ? 'var(--bullish)' : 'var(--bearish)'
            }}>
              {netPnL >= 0 ? '+' : ''}${netPnL.toFixed(2)}
            </h4>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Balance: <strong style={{ color: 'var(--text-main)' }}>${balance.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</strong>
            </span>
          </div>
        </div>

        {/* Win Rate Card */}
        <div className="glass-card" style={styles.statCard}>
          <CheckCircle2 size={28} style={{ color: 'var(--accent-purple)' }} />
          <div style={{ flexGrow: 1 }}>
            <span style={styles.statLabel}>Win Rate</span>
            <h4 style={styles.statVal}>{winRate.toFixed(1)}%</h4>
            
            {/* Visual Win Rate progress bar */}
            <div style={{ width: '100%', height: '6px', backgroundColor: 'rgba(255,255,255,0.05)', borderRadius: '3px', marginTop: '6px', overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${winRate}%`, backgroundColor: 'var(--accent-purple)', borderRadius: '3px', transition: 'width 0.5s ease-out' }} />
            </div>
          </div>
        </div>

        {/* Profit Factor Card */}
        <div className="glass-card" style={styles.statCard}>
          <DollarSign size={28} style={{ color: pfColor }} />
          <div style={{ flexGrow: 1 }}>
            <span style={styles.statLabel}>Profit Factor</span>
            <h4 style={{ ...styles.statVal, color: pfColor }}>
              {totalTrades > 0 && Math.abs(grossLosses) === 0 ? '∞' : profitFactor.toFixed(2)}
            </h4>
            <span style={{ fontSize: '0.75rem', color: pfColor, fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              {pfLabel}
            </span>
          </div>
        </div>

        {/* Trade Count Summary Card */}
        <div className="glass-card" style={styles.statCard}>
          <Activity size={28} style={{ color: 'var(--accent-blue)' }} />
          <div style={{ flexGrow: 1 }}>
            <span style={styles.statLabel}>Total Trades</span>
            <h4 style={styles.statVal}>{totalTrades}</h4>
            <div style={{ display: 'flex', gap: '8px', fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '4px' }}>
              <span>W: <strong style={{ color: 'var(--bullish)' }}>{wins}</strong></span>
              <span>L: <strong style={{ color: 'var(--bearish)' }}>{losses}</strong></span>
              <span>BE: <strong style={{ color: 'var(--text-muted)' }}>{breakEvens}</strong></span>
            </div>
          </div>
        </div>

      </div>

      {/* 3. Detailed Stats Drawer (Averages & Extremes) */}
      <div className="glass-card" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '20px', padding: '16px 24px' }}>
        <div>
          <span style={{ ...styles.statLabel, fontSize: '0.7rem' }}>Avg. Trade PnL</span>
          <span style={{ fontSize: '1rem', fontWeight: '700', color: avgPnL >= 0 ? 'var(--bullish)' : 'var(--bearish)' }}>
            {avgPnL >= 0 ? '+' : ''}${avgPnL.toFixed(2)}
          </span>
        </div>
        <div>
          <span style={{ ...styles.statLabel, fontSize: '0.7rem' }}>Largest Win</span>
          <span style={{ fontSize: '1rem', fontWeight: '700', color: 'var(--bullish)' }}>
            {maxWin > 0 ? `+$${maxWin.toFixed(2)}` : '$0.00'}
          </span>
        </div>
        <div>
          <span style={{ ...styles.statLabel, fontSize: '0.7rem' }}>Largest Loss</span>
          <span style={{ fontSize: '1rem', fontWeight: '700', color: 'var(--bearish)' }}>
            {maxLoss < 0 ? `-$${Math.abs(maxLoss).toFixed(2)}` : '$0.00'}
          </span>
        </div>
        <div>
          <span style={{ ...styles.statLabel, fontSize: '0.7rem' }}>Gross Profits</span>
          <span style={{ fontSize: '1rem', fontWeight: '700', color: 'var(--bullish)' }}>
            +${grossProfits.toFixed(2)}
          </span>
        </div>
        <div>
          <span style={{ ...styles.statLabel, fontSize: '0.7rem' }}>Gross Losses</span>
          <span style={{ fontSize: '1rem', fontWeight: '700', color: 'var(--bearish)' }}>
            -${Math.abs(grossLosses).toFixed(2)}
          </span>
        </div>
      </div>

      {/* 4. Filter Panel & Table Card */}
      <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        
        {/* Interactive Filters Bar */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '15px' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'center' }}>
            
            {/* Filter Symbol */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: '500' }}>Symbol:</span>
              <select 
                value={symbolFilter} 
                className="form-select"
                style={{ width: '120px', padding: '6px 28px 6px 12px', fontSize: '0.8rem' }}
                onChange={e => setSymbolFilter(e.target.value)}
              >
                {uniqueSymbols.map(s => <option key={s} value={s}>{s === 'ALL' ? 'All Symbols' : s.replace('USDT','')}</option>)}
              </select>
            </div>

            {/* Filter Type */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: '500' }}>Type:</span>
              <select 
                value={typeFilter} 
                className="form-select"
                style={{ width: '100px', padding: '6px 28px 6px 12px', fontSize: '0.8rem' }}
                onChange={e => setTypeFilter(e.target.value)}
              >
                <option value="ALL">All Types</option>
                <option value="long">Longs</option>
                <option value="short">Shorts</option>
              </select>
            </div>

            {/* Filter Status */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: '500' }}>Outcome:</span>
              <select 
                value={statusFilter} 
                className="form-select"
                style={{ width: '100px', padding: '6px 28px 6px 12px', fontSize: '0.8rem' }}
                onChange={e => setStatusFilter(e.target.value)}
              >
                <option value="ALL">All Status</option>
                <option value="TP">TP (Target)</option>
                <option value="SL">SL (Stop)</option>
                <option value="BE">BE (Breakeven)</option>
              </select>
            </div>

          </div>

          {/* Sort Control */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: '500' }}>Sort By:</span>
            <select 
              value={sortBy} 
              className="form-select"
              style={{ width: '150px', padding: '6px 28px 6px 12px', fontSize: '0.8rem' }}
              onChange={e => setSortBy(e.target.value)}
            >
              <option value="newest">Newest Exits</option>
              <option value="oldest">Oldest Exits</option>
              <option value="pnl_desc">PnL (High to Low)</option>
              <option value="pnl_asc">PnL (Low to High)</option>
            </select>
          </div>
        </div>

        {/* Datatable */}
        {paginatedTrades.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
            <div style={styles.tableWrapper}>
              <table style={styles.table}>
                <thead>
                  <tr style={styles.tr}>
                    <th style={styles.th}>Asset</th>
                    <th style={styles.th}>Type</th>
                    <th style={styles.th}>Entry / Exit Time</th>
                    <th style={styles.th}>Duration</th>
                    <th style={styles.th}>Prices (Entry / Exit)</th>
                    <th style={styles.th}>Size / Risk</th>
                    <th style={styles.th}>Result</th>
                    <th style={styles.th}>Realized PnL</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedTrades.map((trade, idx) => {
                    const isProfit = trade.pnl > 0;
                    const isLoss = trade.pnl < 0;
                    const badgeClass = trade.status === 'TP' ? 'badge-bullish' : trade.status === 'SL' ? 'badge-bearish' : 'badge-neutral';
                    
                    return (
                      <tr key={idx} style={styles.tr} className="coin-row-hover">
                        <td style={{ ...styles.td, fontWeight: '700' }}>
                          {trade.symbol}
                        </td>
                        <td style={styles.td}>
                          <span className={`badge ${trade.type === 'long' ? 'badge-bullish' : 'badge-bearish'}`} style={{ fontSize: '0.65rem', padding: '2px 8px' }}>
                            {trade.type.toUpperCase()}
                          </span>
                        </td>
                        <td style={{ ...styles.td, fontSize: '0.8rem' }}>
                          <div>Entry: {formatTimestamp(trade.entry_time)}</div>
                          <div style={{ color: 'var(--text-muted)', marginTop: '2px' }}>Exit: {formatTimestamp(trade.exit_time)}</div>
                        </td>
                        <td style={styles.td}>
                          {formatDuration(trade.entry_time, trade.exit_time)}
                        </td>
                        <td style={{ ...styles.td, fontSize: '0.85rem' }}>
                          <div>Entry: ${formatPrice(trade.entry_price)}</div>
                          <div style={{ color: 'var(--text-muted)', marginTop: '2px' }}>Exit: ${formatPrice(trade.exit_price)}</div>
                        </td>
                        <td style={{ ...styles.td, fontSize: '0.85rem' }}>
                          <div>Size: {trade.size.toLocaleString(undefined, {maximumFractionDigits: 6})}</div>
                          <div style={{ color: 'var(--text-muted)', marginTop: '2px' }}>Risk: ${trade.risk_amount.toFixed(2)}</div>
                        </td>
                        <td style={styles.td}>
                          <span className={`badge ${badgeClass}`} style={{ fontSize: '0.65rem', padding: '2px 8px' }}>
                            {trade.status}
                          </span>
                        </td>
                        <td style={{ 
                          ...styles.td, 
                          color: isProfit ? 'var(--bullish)' : isLoss ? 'var(--bearish)' : 'var(--text-muted)',
                          fontWeight: '800',
                          fontSize: '0.95rem'
                        }}>
                          {trade.pnl > 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '10px' }}>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  Showing {(currentPage - 1) * itemsPerPage + 1} - {Math.min(currentPage * itemsPerPage, sortedTrades.length)} of {sortedTrades.length} trades
                </span>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button 
                    onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                    disabled={currentPage === 1}
                    className="btn-secondary"
                    style={{ padding: '6px 12px', fontSize: '0.8rem', opacity: currentPage === 1 ? 0.5 : 1, cursor: currentPage === 1 ? 'not-allowed' : 'pointer' }}
                  >
                    Previous
                  </button>
                  <span style={{ display: 'flex', alignItems: 'center', fontSize: '0.8rem', fontWeight: '600', padding: '0 8px' }}>
                    Page {currentPage} of {totalPages}
                  </span>
                  <button 
                    onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
                    disabled={currentPage === totalPages}
                    className="btn-secondary"
                    style={{ padding: '6px 12px', fontSize: '0.8rem', opacity: currentPage === totalPages ? 0.5 : 1, cursor: currentPage === totalPages ? 'not-allowed' : 'pointer' }}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div style={styles.emptyState}>
            <AlertCircle size={32} style={{ color: 'var(--text-dark)' }} />
            <h4 style={{ color: 'var(--text-main)', marginTop: '8px' }}>No Trades Found</h4>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No completed trades match the selected filter criteria.</p>
          </div>
        )}

      </div>
    </div>
  );
}

function SettingsPanel({ config, saveConfig }) {
  const [localConfig, setLocalConfig] = useState({ ...config });

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLocalConfig({ ...config });
  }, [config]);

  const handleSubmit = (e) => {
    e.preventDefault();
    saveConfig(localConfig);
  };

  return (
    <div className="glass-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px' }}>
        <SettingsIcon size={18} style={{ color: 'var(--accent-purple)' }} />
        <h3 style={styles.cardTitle}>Configuration Settings</h3>
      </div>
      
      <form onSubmit={handleSubmit}>
        <div style={styles.formSectionTitle}>
          <Key size={14} /> Binance API Credentials
        </div>
        
        <div className="form-group">
          <label>Binance API Key</label>
          <input 
            type="password" 
            value={localConfig.binance_api_key} 
            className="form-input"
            onChange={e => setLocalConfig(prev => ({ ...prev, binance_api_key: e.target.value }))}
            placeholder="Binance API Key (optional for paper)"
          />
        </div>

        <div className="form-group">
          <label>Binance Secret Key</label>
          <input 
            type="password" 
            value={localConfig.binance_api_secret} 
            className="form-input"
            onChange={e => setLocalConfig(prev => ({ ...prev, binance_api_secret: e.target.value }))}
            placeholder="Binance Secret Key (optional for paper)"
          />
        </div>

        <div className="form-group" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <label style={{ margin: 0 }}>Use Binance Testnet</label>
          <label className="switch">
            <input 
              type="checkbox" 
              checked={localConfig.testnet}
              onChange={e => setLocalConfig(prev => ({ ...prev, testnet: e.target.checked }))}
            />
            <span className="slider"></span>
          </label>
        </div>

        <div className="form-group" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '10px' }}>
          <label style={{ margin: 0 }}>Portfolio Margin Account</label>
          <label className="switch">
            <input 
              type="checkbox" 
              checked={localConfig.portfolio_margin || false}
              onChange={e => setLocalConfig(prev => ({ ...prev, portfolio_margin: e.target.checked }))}
            />
            <span className="slider"></span>
          </label>
        </div>

        <div style={{ ...styles.formSectionTitle, marginTop: '20px' }}>
          <Activity size={14} /> Bot Parameters
        </div>

        <div className="form-group">
          <label>Trading Mode</label>
          <select 
            value={localConfig.trading_mode} 
            className="form-select"
            onChange={e => setLocalConfig(prev => ({ ...prev, trading_mode: e.target.value }))}
          >
            <option value="paper">Paper (Simulation)</option>
            <option value="live">Live (Binance API Orders)</option>
          </select>
        </div>

        <div className="form-group">
          <label>Market Type</label>
          <select 
            value={localConfig.market_type} 
            className="form-select"
            onChange={e => setLocalConfig(prev => ({ ...prev, market_type: e.target.value }))}
          >
            <option value="futures">USDⓈ-M Futures (Supports Shorts)</option>
            <option value="spot">Spot (Long-only)</option>
          </select>
        </div>

        <div className="form-group">
          <label>Monitored Symbol</label>
          <select 
            value={localConfig.symbol} 
            className="form-select"
            onChange={e => setLocalConfig(prev => ({ ...prev, symbol: e.target.value }))}
          >
            {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        <div className="form-group">
          <label>Candle Timeframe</label>
          <select 
            value={localConfig.timeframe} 
            className="form-select"
            onChange={e => setLocalConfig(prev => ({ ...prev, timeframe: e.target.value }))}
          >
            {TIMEFRAMES.map(tf => <option key={tf} value={tf}>{tf}</option>)}
          </select>
        </div>

        <div className="form-group">
          <label>Risk Per Trade (%)</label>
          <input 
            type="number" 
            step="0.1"
            value={localConfig.risk_pct} 
            className="form-input"
            onChange={e => setLocalConfig(prev => ({ ...prev, risk_pct: parseFloat(e.target.value) || 1.0 }))}
          />
        </div>

        <div className="form-group">
          <label>Risk Reward Ratio (R)</label>
          <input 
            type="number" 
            step="0.5"
            value={localConfig.rr_ratio} 
            className="form-input"
            onChange={e => setLocalConfig(prev => ({ ...prev, rr_ratio: parseFloat(e.target.value) || 2.0 }))}
          />
        </div>

        <div className="form-group">
          <label>Peak Drawdown Exit (%)</label>
          <input 
            type="number" 
            step="0.1"
            value={localConfig.peak_drawdown_exit_pct ?? 4.0} 
            className="form-input"
            onChange={e => setLocalConfig(prev => ({ ...prev, peak_drawdown_exit_pct: parseFloat(e.target.value) || 4.0 }))}
          />
          <small style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
            Close a winning trade if it pulls back more than this percentage from its peak.
          </small>
        </div>

        <div className="form-group">
          <label>Max Trade Loss (USD)</label>
          <input 
            type="number" 
            step="1"
            value={localConfig.max_trade_loss_usd ?? 35.0} 
            className="form-input"
            onChange={e => setLocalConfig(prev => ({ ...prev, max_trade_loss_usd: parseFloat(e.target.value) || 0.0 }))}
          />
          <small style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
            Cap the dollar risk per trade. Set to 0 to disable.
          </small>
        </div>

        <div className="form-group">
          <label>Max Concurrent Trades</label>
          <input 
            type="number" 
            step="1"
            value={localConfig.max_active_trades || 5} 
            className="form-input"
            onChange={e => setLocalConfig(prev => ({ ...prev, max_active_trades: parseInt(e.target.value) || 5 }))}
          />
        </div>

        <div style={{ marginTop: '20px' }}>
          <button type="submit" className="btn-secondary" style={{ width: '100%', justifyContent: 'center' }}>
            Save Configuration
          </button>
        </div>
      </form>
    </div>
  );
}

const styles = {
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '20px 40px',
    borderBottom: '1px solid var(--border-color)',
    background: 'rgba(10, 11, 16, 0.5)',
    backdropFilter: 'blur(10px)',
  },
  brand: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  title: {
    fontSize: '1.4rem',
    fontWeight: '800',
    letterSpacing: '-0.02em',
    color: 'var(--text-main)',
  },
  tagline: {
    fontSize: '0.8rem',
    color: 'var(--text-dark)',
    marginLeft: '12px',
    borderLeft: '1px solid var(--border-color)',
    paddingLeft: '12px',
  },
  nav: {
    display: 'flex',
    gap: '8px',
  },
  navBtn: {
    background: 'transparent',
    border: 'none',
    color: 'var(--text-muted)',
    padding: '10px 18px',
    borderRadius: '10px',
    cursor: 'pointer',
    fontWeight: '600',
    fontSize: '0.9rem',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    transition: 'background-color 0.2s, color 0.2s',
  },
  navActive: {
    background: 'rgba(255, 255, 255, 0.05)',
    color: 'var(--text-main)',
    border: '1px solid var(--border-color)',
  },
  mainContent: {
    padding: '40px',
    flexGrow: 1,
    display: 'flex',
    flexDirection: 'column',
  },
  dashboardGrid: {
    display: 'grid',
    gridTemplateColumns: '220px 260px minmax(240px, 1fr)',
    gridAutoRows: 'minmax(min-content, max-content)',
    gap: '18px',
    alignItems: 'start',
    minWidth: 0,
    width: '100%',
    justifyContent: 'space-between',
  },
  controlCard: {
    position: 'relative',
    overflow: 'hidden',
    minWidth: 0,
    minHeight: 0,
  },
  activeGlow: {
    borderColor: 'rgba(16, 185, 129, 0.3)',
    boxShadow: '0 0 25px rgba(16, 185, 129, 0.08)',
  },
  cardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '20px',
  },
  cardTitle: {
    fontSize: '1.05rem',
    fontWeight: '600',
    color: 'var(--text-main)',
  },
  statusDot: {
    width: '10px',
    height: '10px',
    borderRadius: '50%',
    display: 'inline-block',
  },
  statusRow: {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '12px 0',
    borderBottom: '1px solid var(--border-color)',
  },
  statusCell: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  statusLabel: {
    fontSize: '0.75rem',
    color: 'var(--text-muted)',
    textTransform: 'uppercase',
  },
  statusValue: {
    fontSize: '0.95rem',
    fontWeight: '700',
  },
  actionButtons: {
    marginTop: '20px',
  },
  scanStatusBarTop: {
    display: 'flex',
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'stretch',
    gap: '16px',
    padding: '16px 20px',
    borderRadius: '16px',
    margin: '20px 20px 0',
    background: 'rgba(15, 23, 42, 0.95)',
    border: '1px solid rgba(148, 163, 184, 0.16)',
    boxShadow: '0 14px 40px rgba(0, 0, 0, 0.18)',
    width: '100%',
    minWidth: 0,
    overflowX: 'auto',
    WebkitOverflowScrolling: 'touch',
  },
  scanStatusBar: {
    display: 'flex',
    justifyContent: 'space-between',
    gap: '18px',
    padding: '16px 20px',
    borderRadius: '16px',
    marginBottom: '20px',
    background: 'rgba(15, 23, 42, 0.85)',
    border: '1px solid rgba(148, 163, 184, 0.12)',
    alignItems: 'center',
  },
  scanStatusItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    flex: '1 1 170px',
    minWidth: '150px',
    maxWidth: '240px',
  },
  scanStatusLabel: {
    fontSize: '0.62rem',
    color: 'var(--text-dark)',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
  },
  scanProgressTrack: {
    width: '100%',
    height: '5px',
    borderRadius: '999px',
    background: 'rgba(255, 255, 255, 0.08)',
    overflow: 'hidden',
    marginTop: '4px',
  },
  scanProgressFill: {
    height: '100%',
    borderRadius: '999px',
    background: 'linear-gradient(90deg, rgba(16,185,129,1) 0%, rgba(79,70,229,1) 100%)',
    transition: 'width 0.25s ease',
  },
  scanStatusValue: {
    fontSize: '0.9rem',
    color: 'var(--text-main)',
    fontWeight: '700',
    lineHeight: '1.1',
  },
  scanStatusSecondary: {
    fontSize: '0.75rem',
    color: 'var(--text-muted)',
    lineHeight: '1.2',
    maxWidth: '100%',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  scanSkippedLabel: {
    fontSize: '0.8rem',
    color: 'var(--text-muted)',
    marginTop: '4px',
  },
  emptyState: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '40px 20px',
    textAlign: 'center',
    gap: '12px',
  },
  positionDetails: {
    display: 'flex',
    flexDirection: 'column',
    gap: '15px',
    marginTop: '15px',
  },
  positionHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  entryTime: {
    fontSize: '0.8rem',
    color: 'var(--text-muted)',
  },
  metricGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '16px',
    padding: '12px 0',
  },
  metricLabel: {
    display: 'block',
    fontSize: '0.75rem',
    color: 'var(--text-muted)',
    marginBottom: '4px',
  },
  metricValue: {
    fontSize: '1.05rem',
    fontWeight: '700',
  },
  floatingPnl: {
    border: '1px solid',
    borderRadius: '10px',
    padding: '12px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '4px',
  },
  pnlLabel: {
    fontSize: '0.75rem',
    color: 'var(--text-muted)',
  },
  pnlValue: {
    fontSize: '1.2rem',
    fontWeight: '800',
  },
  formSectionTitle: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    fontSize: '0.8rem',
    fontWeight: '700',
    color: 'var(--text-muted)',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    marginBottom: '14px',
    borderBottom: '1px solid var(--border-color)',
    paddingBottom: '6px',
  },
  consoleCard: {
    background: '#040507',
    padding: '16px',
    maxHeight: '300px',
    display: 'flex',
    flexDirection: 'column',
  },
  consoleHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '12px',
  },
  refreshBtn: {
    background: 'transparent',
    border: 'none',
    color: 'var(--text-dark)',
    cursor: 'pointer',
  },
  consoleContent: {
    flexGrow: 1,
    overflowY: 'auto',
    fontFamily: 'var(--font-mono)',
    fontSize: '0.8rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  logRow: {
    display: 'flex',
    gap: '10px',
    lineHeight: '1.4',
  },
  logTime: {
    color: 'var(--text-dark)',
    flexShrink: 0,
  },
  logLevel: {
    fontWeight: '600',
    flexShrink: 0,
  },
  logMsg: {
    color: 'var(--text-main)',
    whiteSpace: 'pre-wrap',
  },
  chartFallback: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'rgba(0,0,0,0.3)',
    border: '1px dashed var(--border-color)',
    borderRadius: '12px',
    padding: '20px',
    textAlign: 'center',
    color: 'var(--text-muted)',
    gap: '8px',
  },
  backtestContainer: {
    display: 'flex',
    flexDirection: 'column',
    gap: '24px',
  },
  backtestConfigCard: {
    maxWidth: '1000px',
  },
  backtestFormGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
    gap: '16px',
  },
  backtestResultsArea: {
    display: 'flex',
    flexDirection: 'column',
    gap: '24px',
  },
  statsSummaryGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: '16px',
  },
  statCard: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
    padding: '20px',
  },
  statLabel: {
    fontSize: '0.8rem',
    color: 'var(--text-muted)',
    display: 'block',
    marginBottom: '2px',
  },
  statVal: {
    fontSize: '1.3rem',
    fontWeight: '800',
  },
  smallPct: {
    fontSize: '0.9rem',
    fontWeight: '600',
  },
  tableWrapper: {
    overflowX: 'auto',
    marginTop: '10px',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    textAlign: 'left',
    fontSize: '0.9rem',
  },
  th: {
    padding: '12px 16px',
    borderBottom: '1px solid var(--border-color)',
    color: 'var(--text-muted)',
    fontWeight: '600',
  },
  td: {
    padding: '12px 16px',
    borderBottom: '1px solid var(--border-color)',
    color: 'var(--text-main)',
  },
  tr: {
    transition: 'background-color 0.2s',
  },
};
