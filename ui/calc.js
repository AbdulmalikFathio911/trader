/* MT5 lot calculator for the browser.
 *
 * A line-by-line port of .claude/skills/mt5-lot-calculator/calc.py, so the page and the
 * /trade skill give the same numbers. Arithmetic only: it never touches the network and
 * never places, modifies or closes an order. Needs decimal.js (exact decimal arithmetic),
 * vendored in ui/vendor/decimal.js and inlined into the page by ui/build.py.
 *
 * MT5Calc.calculate(input) -> result object with verdict OK | NO_TRADE | INVALID.
 * input keys mirror the calc.py flags with underscores: symbol, side, entry, stop, target,
 * rr, lots, balance, risk_pct, free_margin, leverage, contract_size, min_lot, lot_step,
 * digits, stops_level, calc_mode, quote_to_account, current_price. Pass numbers as strings.
 */
(function (root) {
  'use strict';

  var Base = root.Decimal || (typeof require === 'function' ? require('decimal.js') : null);
  if (!Base) { root.MT5Calc = null; return; }

  // Python's decimal module defaults: 28 significant digits, round half even.
  var D = Base.clone({ precision: 28, rounding: Base.ROUND_HALF_EVEN });
  var DOWN = Base.ROUND_DOWN, HALF_UP = Base.ROUND_HALF_UP, HALF_EVEN = Base.ROUND_HALF_EVEN;
  var CEIL = Base.ROUND_CEIL, FLOOR = Base.ROUND_FLOOR;

  var LEVERAGED_MODES = ['forex', 'cfd_leverage'];
  var CALC_MODES = ['forex', 'cfd_leverage', 'cfd', 'stocks'];
  var PLAIN_NUMBER = /^[+-]?(\d+\.?\d*|\.\d+)$/;
  var DEFAULTS = { risk_pct: '1', leverage: '1', min_lot: '0.01', lot_step: '0.01',
                   stops_level: '0', quote_to_account: '1' };
  var NUMERIC = ['entry', 'stop', 'target', 'rr', 'lots', 'balance', 'risk_pct', 'free_margin',
                 'leverage', 'contract_size', 'min_lot', 'lot_step', 'stops_level',
                 'quote_to_account', 'current_price'];

  function text(value) {
    return value === null || value === undefined ? '' : String(value).trim();
  }

  // A number as it was typed: { d: Decimal, t: plain text, dec: decimals typed }.
  function parse(raw) {
    var t = text(raw);
    if (t === '') return null;
    if (!PLAIN_NUMBER.test(t)) return undefined;
    var negative = t.charAt(0) === '-';
    t = t.replace(/^[+-]/, '');
    if (t.charAt(0) === '.') t = '0' + t;
    if (t.charAt(t.length - 1) === '.') t = t.slice(0, -1);
    t = t.replace(/^0+(?=\d)/, '');
    var dot = t.indexOf('.');
    return { d: new D((negative ? '-' : '') + t), t: (negative ? '-' : '') + t,
             dec: dot < 0 ? 0 : t.length - dot - 1 };
  }

  function invalidArguments(message) {
    return { verdict: 'INVALID', errors: [{ code: 'BAD_ARGUMENTS', message: message }], warnings: [] };
  }

  function money(value) { return value.toFixed(2, HALF_UP); }
  function oneDecimal(value) { return value.toFixed(1, HALF_UP); }

  function calculate(input) {
    input = input || {};
    var a = {};
    var i, key, parsed;
    for (i = 0; i < NUMERIC.length; i++) {
      key = NUMERIC[i];
      parsed = parse(input[key]);
      if (parsed === undefined) return invalidArguments('not a number: ' + key + ' = ' + text(input[key]));
      if (parsed === null && DEFAULTS[key] !== undefined) parsed = parse(DEFAULTS[key]);
      a[key] = parsed;
    }
    a.symbol = text(input.symbol);
    a.side = text(input.side);
    a.calc_mode = text(input.calc_mode) || 'forex';
    if (!a.symbol) return invalidArguments('symbol is required');
    if (a.side !== 'buy' && a.side !== 'sell') return invalidArguments('side must be buy or sell');
    if (CALC_MODES.indexOf(a.calc_mode) < 0) return invalidArguments('unknown calc_mode: ' + a.calc_mode);
    if (!a.entry) return invalidArguments('entry is required');
    if (!a.contract_size) return invalidArguments('contract_size is required');
    var digitsText = text(input.digits);
    if (!/^[+-]?\d+$/.test(digitsText)) return invalidArguments('digits must be a whole number');
    a.digits = parseInt(digitsText, 10);

    var invalid = [];   // wrong or missing inputs  -> INVALID
    var blocked = [];   // valid inputs, rule fails -> NO_TRADE
    var warnings = [];
    function bad(code, message) { invalid.push({ code: code, message: message }); }
    function block(code, message) { blocked.push({ code: code, message: message }); }
    function warn(code, message) { warnings.push({ code: code, message: message }); }

    var buy = a.side === 'buy';
    var sign = new D(buy ? 1 : -1);   // direction in which the trade profits
    var HUNDRED = new D(100);

    var out = {
      verdict: null,
      symbol: a.symbol,
      side: a.side,
      calc_mode: a.calc_mode,
      order_type: null,
      lots: null,
      figures_at_lots: null,
      sizing_basis: null,
      entry: a.entry.t,
      stop_loss: a.stop ? a.stop.t : null,
      stop_derived: false,
      take_profit: a.target ? a.target.t : null,
      target_derived: false,
      stop_distance: null,
      stop_points: null,
      budget: null,
      risk: null,
      risk_pct: null,
      reward: null,
      reward_risk: null,
      reward_risk_raw: null,
      breakeven_win_rate_pct: null,
      margin: null,
      free_margin: a.free_margin ? a.free_margin.t : null,
      free_margin_after: null,
      min_lot_risk: null,
      min_lot_risk_pct: null,
      widest_stop_at_min_lot: null,
      ticket: null,
      ticket_text: null,
      errors: [],
      warnings: warnings
    };

    function finish() {
      out.errors = invalid.concat(blocked);
      out.verdict = invalid.length ? 'INVALID' : (blocked.length ? 'NO_TRADE' : 'OK');
      if (out.verdict === 'OK') {
        var ticket = {
          'Symbol': a.symbol,
          'Type': out.order_type || 'UNKNOWN (pass --current-price)',
          'Volume': out.lots,
          'Price': out.entry,
          'Stop Loss': out.stop_loss,
          'Take Profit': out.take_profit || '-'
        };
        out.ticket = ticket;
        out.ticket_text = Object.keys(ticket).map(function (label) {
          var head = label + ':';
          while (head.length < 13) head += ' ';
          return head + ticket[label];
        }).join('\n');
      }
      return out;
    }

    // ---- input validation ---------------------------------------------------
    var positive = ['entry', 'stop', 'target', 'rr', 'lots', 'balance', 'risk_pct', 'leverage',
                    'contract_size', 'min_lot', 'lot_step', 'quote_to_account', 'current_price'];
    for (i = 0; i < positive.length; i++) {
      key = positive[i];
      if (a[key] && a[key].d.lte(0)) {
        bad('NOT_POSITIVE', '--' + key.replace(/_/g, '-') + ' must be greater than zero, got ' + a[key].t);
      }
    }
    if (a.stops_level.d.lt(0)) bad('NOT_POSITIVE', '--stops-level cannot be negative, got ' + a.stops_level.t);
    if (!(a.digits >= 0 && a.digits <= 10)) bad('BAD_DIGITS', '--digits must be between 0 and 10, got ' + a.digits);
    if (invalid.length) return finish();

    var priced = ['entry', 'stop', 'target', 'current_price'];
    for (i = 0; i < priced.length; i++) {
      key = priced[i];
      if (a[key] && a[key].dec > a.digits) {
        bad('TOO_MANY_DECIMALS', '--' + key.replace(/_/g, '-') + ' ' + a[key].t +
            ' has more decimals than the symbol\'s digits (' + a.digits + ')');
      }
    }

    if (!a.stop && !a.lots) {
      bad('NEED_STOP_OR_LOTS', 'give --stop (to size the lots) or --lots (to derive the stop)');
    }

    if (a.stop) {
      if (buy && a.stop.d.gte(a.entry.d)) {
        bad('STOP_WRONG_SIDE', 'buy: the stop ' + a.stop.t + ' must be below the entry ' + a.entry.t);
      }
      if (!buy && a.stop.d.lte(a.entry.d)) {
        bad('STOP_WRONG_SIDE', 'sell: the stop ' + a.stop.t + ' must be above the entry ' + a.entry.t);
      }
    }

    if (a.target) {
      if (buy && a.target.d.lte(a.entry.d)) {
        bad('TARGET_WRONG_SIDE', 'buy: the target ' + a.target.t + ' must be above the entry ' + a.entry.t);
      }
      if (!buy && a.target.d.gte(a.entry.d)) {
        bad('TARGET_WRONG_SIDE', 'sell: the target ' + a.target.t + ' must be below the entry ' + a.entry.t);
      }
    }

    var lotDecimals = a.lot_step.dec;
    function lotsText(value) { return value.toFixed(lotDecimals, DOWN); }

    if (a.lots && !a.lots.d.mod(a.lot_step.d).isZero()) {
      bad('LOTS_NOT_ON_STEP', '--lots ' + a.lots.t + ' is not a multiple of the lot step ' + a.lot_step.t);
    }

    var budget = null;
    if (a.balance) {
      budget = a.balance.d.times(a.risk_pct.d).div(HUNDRED);
      out.budget = money(budget);
    } else if (!a.stop || !a.lots) {
      bad('MISSING_BALANCE', '--balance is required to compute the risk budget');
    }

    if (invalid.length) return finish();

    var unit = a.contract_size.d.times(a.quote_to_account.d);   // account money per 1.0 price move per lot
    var point = new D(10).pow(-a.digits);

    function towardEntry(price) {   // round a stop to the symbol's digits, toward the entry
      return price.toDecimalPlaces(a.digits, buy ? CEIL : FLOOR);
    }
    function priceText(price) { return price.toFixed(a.digits, HALF_EVEN); }
    function widestStop(lots) {
      return towardEntry(a.entry.d.minus(sign.times(budget).div(lots.times(unit))));
    }

    // ---- lots and stop ------------------------------------------------------
    var stop = a.stop ? a.stop.d : null;
    var stopDecimals = a.stop ? a.stop.dec : a.digits;
    var lots, distance;
    if (a.lots) {
      lots = a.lots.d;
      out.sizing_basis = 'given_lots';
      if (lots.lt(a.min_lot.d)) {
        block('LOTS_BELOW_MIN', '--lots ' + a.lots.t + ' is below the minimum lot ' + a.min_lot.t);
        if (budget !== null) out.widest_stop_at_min_lot = priceText(widestStop(a.min_lot.d));
      }
      if (stop === null && !blocked.length) {
        stop = widestStop(lots);
        out.stop_derived = true;
        out.stop_loss = priceText(stop);
        if (stop.eq(a.entry.d)) {
          block('STOP_AT_ENTRY', 'the budget ' + money(budget) + ' is too small for ' + a.lots.t +
                ' lots: the stop would sit on the entry price');
        } else if (stop.lte(0)) {
          bad('STOP_NOT_POSITIVE', 'the derived stop price is not above zero');
        }
      }
    } else {
      distance = a.entry.d.minus(stop).abs();
      var rawLots = budget.div(distance.times(unit));
      lots = rawLots.div(a.lot_step.d).floor().times(a.lot_step.d);
      out.sizing_basis = 'risk_sized';
    }

    out.lots = lotsText(lots);
    if (invalid.length || stop === null || stop.eq(a.entry.d)) return finish();

    distance = a.entry.d.minus(stop).abs();
    out.stop_distance = distance.toFixed(Math.max(a.entry.dec, stopDecimals));
    out.stop_points = distance.div(point).toFixed(0, DOWN);

    var figuresLots = lots;
    if (!a.lots && lots.lt(a.min_lot.d)) {
      figuresLots = a.min_lot.d;
      out.sizing_basis = 'min_lot';
      var minLotRisk = a.min_lot.d.times(unit).times(distance);
      out.min_lot_risk = money(minLotRisk);
      out.min_lot_risk_pct = oneDecimal(minLotRisk.div(a.balance.d).times(HUNDRED));
      out.widest_stop_at_min_lot = priceText(widestStop(a.min_lot.d));
      block('LOTS_BELOW_MIN', 'the budget ' + money(budget) + ' buys ' + lotsText(lots) +
            ' lots at this stop; the minimum lot is ' + a.min_lot.t + ' and would risk ' +
            out.min_lot_risk + ' (' + out.min_lot_risk_pct + '% of the balance). The widest stop ' +
            'that fits the budget at the minimum lot is ' + out.widest_stop_at_min_lot + '. ' +
            'Risk, reward and margin below are shown at the minimum lot.');
    }
    out.figures_at_lots = lotsText(figuresLots);

    // ---- risk ---------------------------------------------------------------
    var risk = figuresLots.times(unit).times(distance);
    out.risk = money(risk);
    if (a.balance) out.risk_pct = money(risk.div(a.balance.d).times(HUNDRED));
    if (a.lots && budget !== null && risk.gt(budget)) {
      warn('RISK_OVER_BUDGET', 'the given lots risk ' + money(risk) + ', over the budget ' +
           money(budget) + ' (' + a.risk_pct.t + '% of the balance)');
    }
    if (a.lots && budget === null) {
      warn('NO_BUDGET_CHECK', '--balance was not given, so the risk was not checked against a budget');
    }

    // ---- target and reward --------------------------------------------------
    var target = a.target ? a.target.d : null;
    if (target !== null && a.rr) warn('RR_IGNORED', '--target was given, so --rr was ignored');
    if (target === null && a.rr) {
      target = a.entry.d.plus(sign.times(a.rr.d).times(distance)).toDecimalPlaces(a.digits, HALF_UP);
      out.target_derived = true;
      out.take_profit = priceText(target);
      if (target.lte(0)) {
        bad('TARGET_NOT_POSITIVE', 'the derived target price is not above zero');
        return finish();
      }
    }
    if (target === null) {
      warn('NO_TARGET', 'no --target or --rr: reward and reward:risk were not computed');
    } else {
      var targetDistance = target.minus(a.entry.d).abs();
      var reward = figuresLots.times(unit).times(targetDistance);
      var ratio = reward.div(risk);
      out.reward = money(reward);
      out.reward_risk = money(ratio);
      out.reward_risk_raw = ratio.toFixed(4, DOWN);
      out.breakeven_win_rate_pct = oneDecimal(HUNDRED.div(ratio.plus(1)));
      if (a.stops_level.d.gt(0) && targetDistance.div(point).lt(a.stops_level.d)) {
        warn('TARGET_INSIDE_STOPS_LEVEL', 'the target is ' + targetDistance.div(point).toFixed(0, HALF_EVEN) +
             ' points from the entry, under the stops level of ' + a.stops_level.t + ' points');
      }
    }

    // ---- margin -------------------------------------------------------------
    var margin = figuresLots.times(a.contract_size.d).times(a.entry.d).times(a.quote_to_account.d);
    if (LEVERAGED_MODES.indexOf(a.calc_mode) >= 0) {
      margin = margin.div(a.leverage.d);
    } else if (!a.leverage.d.eq(1)) {
      warn('LEVERAGE_IGNORED', 'leverage is not applied in ' + a.calc_mode + ' mode');
    }
    out.margin = money(margin);
    if (!a.free_margin) {
      warn('FREE_MARGIN_NOT_GIVEN', '--free-margin was not given, so the margin was not checked');
    } else {
      out.free_margin_after = money(a.free_margin.d.minus(margin));
      if (margin.gt(a.free_margin.d)) {
        block('MARGIN_EXCEEDS_FREE_MARGIN', 'the margin ' + money(margin) + ' for ' + lotsText(figuresLots) +
              ' lots is more than the free margin ' + a.free_margin.t + '; at least ' + money(margin) + ' is needed');
      }
    }

    // ---- stops level --------------------------------------------------------
    if (a.stops_level.d.gt(0) && distance.div(point).lt(a.stops_level.d)) {
      warn('STOP_INSIDE_STOPS_LEVEL', 'the stop is ' + out.stop_points + ' points from the entry, under the ' +
           'stops level of ' + a.stops_level.t + ' points: MT5 may reject it');
    }

    // ---- order type ---------------------------------------------------------
    if (!a.current_price) {
      warn('NO_CURRENT_PRICE', '--current-price was not given, so the order type is unknown');
    } else {
      var word = buy ? 'Buy' : 'Sell';
      if (a.entry.d.eq(a.current_price.d)) {
        out.order_type = word + ' Market';
      } else {
        var entryAbove = a.entry.d.gt(a.current_price.d);
        var limit = entryAbove !== buy;   // sell above the price, or buy below it
        out.order_type = word + ' ' + (limit ? 'Limit' : 'Stop');
        var gap = a.entry.d.minus(a.current_price.d).abs().div(point);
        if (a.stops_level.d.gt(0) && gap.lt(a.stops_level.d)) {
          warn('ENTRY_INSIDE_STOPS_LEVEL', 'the pending entry is ' + gap.toFixed(0, HALF_EVEN) +
               ' points from the current price, under the stops level of ' + a.stops_level.t + ' points');
        }
      }
    }

    return finish();
  }

  /* Share count for a long stock trade, fixed-fractional method with a position cap:
   * the same rule the /trade skill gets from position_sizer.py
   * (--account-size, --entry, --stop, --risk-pct, --max-position-pct), floored to whole shares. */
  function shareCount(input) {
    var entry = parse(input.entry), stop = parse(input.stop), balance = parse(input.balance);
    var riskPct = parse(input.risk_pct) || parse('1');
    var maxPct = parse(input.max_position_pct);
    if (!entry || !stop || !balance || !entry.d.gt(stop.d) || !stop.d.gt(0)) return null;
    var byRisk = balance.d.times(riskPct.d).div(100).div(entry.d.minus(stop.d)).floor();
    var shares = byRisk, binding = 'risk';
    if (maxPct && maxPct.d.gt(0)) {
      var byCap = balance.d.times(maxPct.d).div(100).div(entry.d).floor();
      if (byCap.lt(byRisk)) { shares = byCap; binding = 'max_position_pct'; }
    }
    return { shares: shares.toFixed(0), by_risk: byRisk.toFixed(0), binding: binding };
  }

  var api = { calculate: calculate, shareCount: shareCount, Decimal: D };
  root.MT5Calc = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
