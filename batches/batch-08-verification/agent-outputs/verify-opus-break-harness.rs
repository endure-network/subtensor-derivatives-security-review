#![allow(clippy::arithmetic_side_effects, clippy::unwrap_used)]
//! Adversarial verification harness (verify-opus): attempts to BREAK the
//! report's "DEFENDED" cross-state claims in regimes it did NOT test:
//!   1. amortize ONE staking pump across MANY short self-closes;
//!   2. the regular in-kind `close_short` vehicle (repay Q from pumped alpha);
//!   3. the LONG mirror cold-A_ref cross-state.
//! Net P&L is summed across ALL attacker-controlled accounts (pumper + every
//! position coldkey), measured in free balance after the whole sequence
//! unwinds to TAO. net>0 ⇒ a real drain the report missed.

use super::mock::*;
use crate::*;
use frame_support::assert_ok;
use sp_core::U256;
use substrate_fixed::types::{I64F64, I96F32, U64F64};
use subtensor_runtime_common::{AlphaBalance, NetUid, TaoBalance, Token};
use subtensor_swap_interface::SwapHandler;

const TAO: u64 = 1_000_000_000;

fn t(v: u64) -> TaoBalance {
    TaoBalance::from(v)
}
fn bal(acc: &U256) -> i128 {
    i128::from(Balances::free_balance(acc).to_u64())
}

fn fresh_cold_subnet(idx: u64, t0: u64, fee: u16) -> NetUid {
    let owner_h = U256::from(600_000 + idx * 2);
    let owner_c = U256::from(600_001 + idx * 2);
    let netuid = add_dynamic_network(&owner_h, &owner_c);
    setup_reserves(netuid, t(t0), AlphaBalance::from(t0));
    let sa = SubtensorModule::get_subnet_account_id(netuid).unwrap();
    add_balance_to_coldkey_account(&sa, t(t0.saturating_mul(6)));
    // skew_pool with price 1.0 keeps weights 0.5/0.5 and sets the fee; it does
    // NOT warm the EMA, so short_t_ref falls back to the live reserve (cold).
    pallet_subtensor_swap::PalSwapInitialized::<Test>::insert(netuid, false);
    assert_ok!(
        pallet_subtensor_swap::Pallet::<Test>::maybe_initialize_palswap(
            netuid,
            Some(U64F64::from_num(1.0)),
        )
    );
    pallet_subtensor_swap::FeeRate::<Test>::insert(netuid, fee);
    SubtensorModule::set_shorts_enabled(true);
    SubtensorModule::set_longs_enabled(true);
    SubtensorModule::set_short_kappa_ppb(900_000_000);
    SubtensorModule::set_long_kappa_ppb(900_000_000);
    assert_eq!(
        SubtensorModule::get_moving_alpha_price(netuid),
        0,
        "cold-EMA precondition: T_ref must fall back to live reserve"
    );
    netuid
}

// ===========================================================================
// BREAK 1: amortize ONE pump across M short self-closes.
// The report's PoC used ONE open per pump. If the per-position gap sums faster
// than the single shared pump round-trip cost, net>0 and F-02 escalates.
// ===========================================================================
fn amortized_pump_attack(idx: u64, m: u64, t0: u64, pump_tao: u64, p_tao: u64, fee: u16) -> i128 {
    let netuid = fresh_cold_subnet(idx, t0, fee);

    let pumper = U256::from(710_000 + idx * 1000);
    let pump_hot = U256::from(711_000 + idx * 1000);
    register_ok_neuron(netuid, pump_hot, pumper, 0);
    add_balance_to_coldkey_account(&pumper, t(pump_tao.saturating_add(t0)));

    let mut colds: Vec<(U256, U256)> = Vec::new();
    for i in 0..m {
        let c = U256::from(720_000 + idx * 1000 + i);
        let h = U256::from(760_000 + idx * 1000 + i);
        add_balance_to_coldkey_account(&c, t(p_tao.saturating_add(10 * TAO)));
        colds.push((c, h));
    }

    // Initial free balance of every attacker-controlled account.
    let mut init: i128 = bal(&pumper);
    for (c, _) in &colds {
        init += bal(c);
    }

    // PUMP once via add_stake (moves SubnetTAO = T_ref up).
    assert_ok!(SubtensorModule::add_stake(
        RuntimeOrigin::signed(pumper),
        pump_hot,
        netuid,
        t(pump_tao)
    ));
    let staked =
        SubtensorModule::get_stake_for_hotkey_and_coldkey_on_subnet(&pump_hot, &pumper, netuid);

    // OPEN M shorts at the (still pumped, EMA-cold) reserve.
    let mut opened = 0u64;
    for (c, h) in &colds {
        if SubtensorModule::open_short(RuntimeOrigin::signed(*c), *h, netuid, t(p_tao), None).is_ok()
        {
            opened += 1;
        }
    }

    // UNPUMP once via remove_stake (lowers SubnetTAO back down).
    let _ = SubtensorModule::remove_stake(RuntimeOrigin::signed(pumper), pump_hot, netuid, staked);

    // CLOSE all M shorts self (cash-settled buyback at the restored reserve).
    let mut closed = 0u64;
    for (c, _) in &colds {
        if SubtensorModule::do_close_short_self(RuntimeOrigin::signed(*c), netuid, 1_000_000_000, None)
            .is_ok()
        {
            closed += 1;
        }
    }

    let mut fin: i128 = bal(&pumper);
    for (c, _) in &colds {
        fin += bal(c);
    }
    let net = fin - init;
    println!(
        "[BREAK1-AMORT] m={m:>3} pump={:>7} P={:>6} opened={opened} closed={closed}  net={net:>14} rao ({:.4} TAO)",
        pump_tao / TAO,
        p_tao / TAO,
        net as f64 / 1e9
    );
    net
}

#[test]
fn break_amortized_pump_short_self_close() {
    new_test_ext(1).execute_with(|| {
        println!("[BREAK1] amortize one pump across M opens. net>0 ⇒ DRAIN (report missed). fee=0, kappa=0.9, T0=A0=20k");
        let t0 = 20_000 * TAO;
        let mut worst: i128 = i128::MIN;
        let mut idx = 0u64;
        for &m in &[1u64, 4, 16] {
            for &pump in &[2_000u64, 10_000] {
                for &p in &[100u64, 500] {
                    let net = amortized_pump_attack(idx, m, t0, pump * TAO, p * TAO, 0);
                    worst = worst.max(net);
                    idx += 1;
                }
            }
        }
        println!("[BREAK1] BEST attacker net across all (m,pump,P) = {worst} rao ({:.6} TAO)", worst as f64 / 1e9);
        assert!(worst <= TAO as i128, "BREAK1 found a cross-state drain: best net {worst} rao");
    });
}

// ===========================================================================
// BREAK 2: regular in-kind close_short vehicle (report left it "not separately
// reproduced"). Pump by staking alpha AT the short's hotkey, open the short,
// then close_short (in-kind) repaying Q from that pumped alpha, and unwind the
// rest. If the inflated retained R=N (booked at the pumped reserve) exceeds the
// real cost of the alpha used to repay, net>0.
// ===========================================================================
fn regular_close_attack(idx: u64, t0: u64, pump_tao: u64, p_tao: u64, fee: u16) -> i128 {
    let netuid = fresh_cold_subnet(idx, t0, fee);
    let trader = U256::from(810_000 + idx * 1000);
    let hot = U256::from(811_000 + idx * 1000);
    register_ok_neuron(netuid, hot, trader, 0);
    add_balance_to_coldkey_account(&trader, t(pump_tao.saturating_add(p_tao).saturating_add(t0)));

    let init = bal(&trader);

    // PUMP: stake alpha AT the short hotkey so it can be used to repay Q in-kind.
    assert_ok!(SubtensorModule::add_stake(
        RuntimeOrigin::signed(trader),
        hot,
        netuid,
        t(pump_tao)
    ));

    // OPEN short at the pumped reserve (inflated N booked into R).
    let opened =
        SubtensorModule::open_short(RuntimeOrigin::signed(trader), hot, netuid, t(p_tao), None)
            .is_ok();

    // Regular IN-KIND close: repays Q alpha from stake at `hot`, returns P+R TAO.
    let closed = if opened {
        SubtensorModule::do_close_short(RuntimeOrigin::signed(trader), netuid, 1_000_000_000, None)
            .is_ok()
    } else {
        false
    };

    // Unwind any leftover staked alpha back to TAO.
    let left =
        SubtensorModule::get_stake_for_hotkey_and_coldkey_on_subnet(&hot, &trader, netuid);
    if left > AlphaBalance::ZERO {
        let _ = SubtensorModule::remove_stake(RuntimeOrigin::signed(trader), hot, netuid, left);
    }

    let net = bal(&trader) - init;
    println!(
        "[BREAK2-INKIND] pump={:>7} P={:>6} opened={opened} closed={closed}  net={net:>14} rao ({:.4} TAO)",
        pump_tao / TAO,
        p_tao / TAO,
        net as f64 / 1e9
    );
    net
}

#[test]
fn break_regular_close_short_cross_state() {
    new_test_ext(1).execute_with(|| {
        println!("[BREAK2] regular in-kind close_short cross-state. net>0 ⇒ DRAIN. fee=0, kappa=0.9, T0=A0=20k");
        let t0 = 20_000 * TAO;
        let mut worst: i128 = i128::MIN;
        let mut idx = 100u64;
        for &pump in &[2_000u64, 10_000, 20_000] {
            for &p in &[200u64, 1_000, 4_000] {
                let net = regular_close_attack(idx, t0, pump * TAO, p * TAO, 0);
                worst = worst.max(net);
                idx += 1;
            }
        }
        println!("[BREAK2] BEST attacker net = {worst} rao ({:.6} TAO)", worst as f64 / 1e9);
        assert!(worst <= TAO as i128, "BREAK2 found a cross-state drain: best net {worst} rao");
    });
}

// ===========================================================================
// BREAK 3: LONG mirror cold-A_ref cross-state (report: "expected defended,
// not separately reproduced"). DUMP the alpha reserve in-block (remove_stake
// sells alpha → SubnetAlphaIn up? add_stake buys alpha out → SubnetAlphaIn
// down). The long capacity/retained scale with A_ref; open a long at a moved
// alpha reserve, restore it, self-close. net>0 ⇒ drain.
// ===========================================================================
fn long_cross_state_attack(idx: u64, t0: u64, move_tao: u64, p_alpha: u64, fee: u16) -> i128 {
    let netuid = fresh_cold_subnet(idx, t0, fee);
    let trader = U256::from(910_000 + idx * 1000);
    let hot = U256::from(911_000 + idx * 1000);
    register_ok_neuron(netuid, hot, trader, 0);
    add_balance_to_coldkey_account(&trader, t(move_tao.saturating_add(t0).saturating_mul(2)));

    // Measure init BEFORE the pump so the full add_stake/remove_stake round-trip
    // cost is captured (NOT after — that would spuriously credit the recovered
    // stake as profit).
    let init = bal(&trader);

    // Trader needs alpha stake at `hot` to post the long collateral P.
    // Acquire it by buying (add_stake) — this also moves the alpha reserve down.
    assert_ok!(SubtensorModule::add_stake(
        RuntimeOrigin::signed(trader),
        hot,
        netuid,
        t(move_tao)
    ));
    let init_alpha =
        SubtensorModule::get_stake_for_hotkey_and_coldkey_on_subnet(&hot, &trader, netuid);

    let a_before = SubnetAlphaIn::<Test>::get(netuid).to_u64();
    let opened = SubtensorModule::open_long(
        RuntimeOrigin::signed(trader),
        hot,
        netuid,
        AlphaBalance::from(p_alpha),
        None,
    )
    .is_ok();
    let a_after_open = SubnetAlphaIn::<Test>::get(netuid).to_u64();

    let closed = if opened {
        SubtensorModule::do_close_long_self(RuntimeOrigin::signed(trader), netuid, 1_000_000_000, None)
            .is_ok()
    } else {
        false
    };

    // Unwind all alpha to TAO so net is measured in one denomination.
    let left =
        SubtensorModule::get_stake_for_hotkey_and_coldkey_on_subnet(&hot, &trader, netuid);
    if left > AlphaBalance::ZERO {
        let _ = SubtensorModule::remove_stake(RuntimeOrigin::signed(trader), hot, netuid, left);
    }
    let net = bal(&trader) - init;
    println!(
        "[BREAK3-LONG] move={:>7} Pα={:>6} opened={opened} closed={closed} a:{}->{} initα={}  net={net} rao ({:.4} TAO)",
        move_tao / TAO,
        p_alpha / TAO,
        a_before / TAO,
        a_after_open / TAO,
        init_alpha.to_u64() / TAO,
        net as f64 / 1e9
    );
    net
}

// F-01 reachability check. Production `get_subnet_terms` sets
// `alpha_in = tao_in / price`, so the emission injection ratio equals `price`
// (NOT the fixed 5:1 ratio `poc_emission_drift_then_leak` forces). STAB-A
// injects that realistic proportional delta; STAB-B seeds a migration-style
// w=0.55 skew. A self-healing or pinned weight ⇒ F-01 stays dormant.
fn weight_quote(netuid: NetUid) -> f64 {
    pallet_subtensor_swap::SwapBalancer::<Test>::get(netuid)
        .get_quote_weight()
        .deconstruct() as f64
        / 1e18
}

fn realistic_emit(netuid: NetUid, emission_tao: u64) {
    let price = <Test as pallet::Config>::SwapInterface::current_alpha_price(netuid.into());
    let pf: f64 = price.to_num::<f64>();
    if pf <= 0.0 {
        return;
    }
    let alpha_delta = (emission_tao as f64 / pf) as u64;
    let (dt, da) = <Test as pallet::Config>::SwapInterface::adjust_protocol_liquidity(
        netuid.into(),
        t(emission_tao),
        AlphaBalance::from(alpha_delta),
    );
    SubnetTAO::<Test>::mutate(netuid, |x| *x = x.saturating_add(dt));
    SubnetAlphaIn::<Test>::mutate(netuid, |x| *x = x.saturating_add(da));
}

#[test]
fn stability_realistic_emission_keeps_weight_pinned() {
    new_test_ext(1).execute_with(|| {
        let netuid = fresh_cold_subnet(900, 100_000 * TAO, 0);
        let w0 = weight_quote(netuid);
        for _ in 0..200 {
            realistic_emit(netuid, 50 * TAO);
        }
        let w1 = weight_quote(netuid);
        println!("[STAB-A] proportional emission x200: w_quote {w0:.6} -> {w1:.6} (drift {:.2e})", (w1 - w0).abs());
        assert!((w1 - 0.5).abs() < 1e-3, "realistic emission drifted weights: {w1}");

        pallet_subtensor_swap::PalSwapInitialized::<Test>::insert(netuid, false);
        assert_ok!(
            pallet_subtensor_swap::Pallet::<Test>::maybe_initialize_palswap(
                netuid,
                Some(U64F64::from_num(1.222)),
            )
        );
        let ws = weight_quote(netuid);
        for _ in 0..400 {
            realistic_emit(netuid, 50 * TAO);
        }
        let we = weight_quote(netuid);
        println!("[STAB-B] seeded skew {ws:.4}; realistic emission x400 -> {we:.6} (toward 0.5 = self-heal, away = amplify)");
    });
}

#[test]
fn break_long_mirror_cross_state() {
    new_test_ext(1).execute_with(|| {
        println!("[BREAK3] long mirror cold-A_ref cross-state. net>0 ⇒ DRAIN. fee=0, kappa=0.9, T0=A0=20k");
        let t0 = 20_000 * TAO;
        let mut worst: i128 = i128::MIN;
        let mut idx = 200u64;
        for &mv in &[2_000u64, 8_000, 16_000] {
            for &p in &[200u64, 1_000] {
                let net = long_cross_state_attack(idx, t0, mv * TAO, p * TAO, 0);
                worst = worst.max(net);
                idx += 1;
            }
        }
        println!("[BREAK3] BEST attacker net = {worst} rao ({:.6} TAO)", worst as f64 / 1e9);
        assert!(worst <= TAO as i128, "BREAK3 found a long cross-state drain: best net {worst} rao");
    });
}
// NOTE: this is the verify-opus break-attempt harness (my 4 tests + helpers).
// The live shared copy also received unrelated tests from a concurrent agent; not included here.
