# 🚨 Alert Calculation & Triggering Logic

## Overview

This document explains **exactly how and when alerts are triggered** in the SwitchOn inspection monitoring system.

---

## 📊 Core Concepts

### Time Windows

The system uses **two distinct time windows** for comparison:

| Window | Duration | Purpose | Time Range |
|--------|----------|---------|------------|
| **Current Window** | 10 minutes | Real-time monitoring | Last 10 minutes from now |
| **Baseline Window** | 60 minutes | Historical comparison | 60-120 minutes ago |

**Example at 12:00 PM:**
```
Timeline:
├─ 10:00 AM ────────┤ 11:00 AM ────────┤ 11:50 AM ──┤ 12:00 PM (now)
   ↑                ↑                   ↑            ↑
   Baseline Start   Baseline End        Current      Current
   (120 min ago)    (60 min ago)        Start        End
                                        (10 min ago)

BASELINE: Events from 10:00-11:00 AM (60 minutes)
CURRENT:  Events from 11:50-12:00 PM (10 minutes)
GAP:      11:00-11:50 AM (not used - prevents contamination)
```

---

## 🔢 Step-by-Step Calculation

### Step 1: Collect Current Events

```sql
SELECT * FROM inspection_events
WHERE line_id = 'line-1'
  AND timestamp >= (NOW - 10 minutes)
  AND timestamp <= NOW
```

**Minimum Requirement:** At least **5 events** must exist
- If fewer than 5 events → **No alert** (insufficient data)

### Step 2: Calculate Current Defect Rate

```
current_defect_rate = (failed_events / total_events)
```

**Example:**
```
Total events in last 10 min: 50
Failed events: 5
Current defect rate = 5/50 = 0.10 = 10%
```

### Step 3: Calculate Baseline Defect Rate

```sql
SELECT * FROM inspection_events
WHERE line_id = 'line-1'
  AND timestamp >= (NOW - 120 minutes)
  AND timestamp < (NOW - 60 minutes)
```

```
baseline_defect_rate = (failed_events / total_events)
```

**Example:**
```
Total events 60-120 min ago: 200
Failed events: 4
Baseline defect rate = 4/200 = 0.02 = 2%
```

**Special Case:** If baseline = 0%, system uses **0.1%** (0.001) to avoid division by zero

### Step 4: Calculate Factor

```
factor = current_defect_rate / baseline_defect_rate
```

**Example:**
```
Factor = 10% / 2% = 5.0x
```

This means the current defect rate is **5 times higher** than the historical baseline.

---

## 🎯 Alert Severity Thresholds

An alert is triggered when **BOTH** conditions are met for any severity level:

### Critical Alert 🔴

| Condition | Threshold | Description |
|-----------|-----------|-------------|
| **Factor** | ≥ 3.0x | Current rate is **at least 3x** the baseline |
| **Absolute** | ≥ 10% | Current defect rate is **at least 10%** |

**Both must be true!**

### Warning Alert 🟡

| Condition | Threshold | Description |
|-----------|-----------|-------------|
| **Factor** | ≥ 2.0x | Current rate is **at least 2x** the baseline |
| **Absolute** | ≥ 5% | Current defect rate is **at least 5%** |

### Info Alert ℹ️

| Condition | Threshold | Description |
|-----------|-----------|-------------|
| **Factor** | ≥ 1.5x | Current rate is **at least 1.5x** the baseline |
| **Absolute** | ≥ 2% | Current defect rate is **at least 2%** |

---

## 📈 Real-World Examples

### Example 1: Critical Alert ✅

**Scenario:** Line-1 suddenly has major quality issues

**Current Window (Last 10 min):**
- Total events: 50
- Failed: 5
- **Current rate: 10%** (5/50)

**Baseline (60-120 min ago):**
- Total events: 200
- Failed: 4
- **Baseline rate: 2%** (4/200)

**Calculation:**
```
Factor = 10% / 2% = 5.0x

Check CRITICAL:
✅ Factor: 5.0x ≥ 3.0x? → YES
✅ Absolute: 10% ≥ 10%? → YES

Result: CRITICAL alert triggered 🔴
```

**Alert Message:**
> "Defect rate 10.0% is 5.0x baseline (2.0%). Detected 5 failures in last 10 minutes."

---

### Example 2: Warning Alert ✅

**Current Window:**
- Total: 100
- Failed: 6
- **Current rate: 6%** (6/100)

**Baseline:**
- Total: 200
- Failed: 4
- **Baseline rate: 2%** (4/200)

**Calculation:**
```
Factor = 6% / 2% = 3.0x

Check CRITICAL:
✅ Factor: 3.0x ≥ 3.0x? → YES
❌ Absolute: 6% ≥ 10%? → NO (fails)

Check WARNING:
✅ Factor: 3.0x ≥ 2.0x? → YES
✅ Absolute: 6% ≥ 5%? → YES

Result: WARNING alert triggered 🟡
```

---

### Example 3: No Alert ❌

**Current Window:**
- Total: 100
- Failed: 2
- **Current rate: 2%** (2/100)

**Baseline:**
- Total: 200
- Failed: 4
- **Baseline rate: 2%** (4/200)

**Calculation:**
```
Factor = 2% / 2% = 1.0x

Check INFO:
❌ Factor: 1.0x ≥ 1.5x? → NO
✅ Absolute: 2% ≥ 2%? → YES

Result: No alert (factor too low) ✅
```

**Why?** Current rate equals baseline - this is normal operation!

---

### Example 4: High Absolute, Low Factor ❌

**Current Window:**
- Total: 50
- Failed: 3
- **Current rate: 6%** (3/50)

**Baseline:**
- Total: 100
- Failed: 5
- **Baseline rate: 5%** (5/100)

**Calculation:**
```
Factor = 6% / 5% = 1.2x

Check WARNING:
❌ Factor: 1.2x ≥ 2.0x? → NO
✅ Absolute: 6% ≥ 5%? → YES

Check INFO:
❌ Factor: 1.2x ≥ 1.5x? → NO
✅ Absolute: 6% ≥ 2%? → YES

Result: No alert ❌
```

**Why?** Even though absolute rate is 6%, it's only **1.2x** the baseline. This is not significant enough to warrant an alert.

---

## 🛡️ Cooldown & Deduplication

**Cooldown Period:** 5 minutes

After an alert is created, **no new alerts** will be triggered for the same line for 5 minutes, even if conditions are met.

**Logic:**
```sql
SELECT * FROM alerts
WHERE line_id = 'line-1'
  AND status = 'active'
  AND created_at >= (NOW - 5 minutes)
```

If an active alert exists within the last 5 minutes → **Skip alert creation**

**Why?** Prevents alert spam when a problem persists.

---

## 📋 Quick Reference Table

**With 2% baseline, here's when alerts fire for 50 events:**

| Failures | Defect Rate | Factor | Alert Level |
|----------|-------------|--------|-------------|
| 0 | 0% | 0x | None ✅ |
| 1 | 2% | 1.0x | None ✅ |
| 2 | 4% | 2.0x | None* ✅ |
| 3 | 6% | 3.0x | WARNING 🟡 |
| 4 | 8% | 4.0x | WARNING 🟡 |
| **5** | **10%** | **5.0x** | **CRITICAL 🔴** |
| 10 | 20% | 10x | CRITICAL 🔴 |
| 25 | 50% | 25x | CRITICAL 🔴 |
| 50 | 100% | 50x | CRITICAL 🔴 |

*2 failures = 4% rate which is 2.0x baseline, but 4% < 5% absolute, so WARNING not triggered. INFO requires ≥1.5x (met) and ≥2% (met), so INFO would trigger.

---

## 🔧 Configuration

All thresholds are configurable in `backend/app/config.py`:

```python
class Settings(BaseSettings):
    # Detection Windows
    min_events: int = 5              # Minimum events required
    window_minutes: int = 10         # Current window size
    baseline_minutes: int = 60       # Baseline window size
    cooldown_minutes: int = 5        # Alert cooldown period

    # Alert Thresholds
    threshold_info_factor: float = 1.5      # INFO: 1.5x baseline
    threshold_info_absolute: float = 0.02   # INFO: 2% absolute

    threshold_warning_factor: float = 2.0   # WARNING: 2x baseline
    threshold_warning_absolute: float = 0.05 # WARNING: 5% absolute

    threshold_critical_factor: float = 3.0   # CRITICAL: 3x baseline
    threshold_critical_absolute: float = 0.10 # CRITICAL: 10% absolute
```

---

## 🎓 Key Takeaways

1. **Dual Thresholds:** Both factor AND absolute rate must be met
2. **Baseline Comparison:** Alerts are relative to historical performance
3. **Time Windows:** Uses past data (60-120 min ago) to avoid contamination
4. **Minimum Data:** Requires at least 5 events to make decisions
5. **Cooldown:** Prevents alert spam with 5-minute cooldown
6. **Severity Hierarchy:** System chooses highest severity that passes both checks

---

## 🧪 Testing Scenarios

### Test 1: Trigger Critical Alert

1. Ensure baseline exists (~2% defect rate)
2. Send **50 events** with **5+ failures** (≥10% rate)
3. Expected: CRITICAL alert within seconds

### Test 2: Trigger Warning Alert

1. Ensure baseline exists (~2% defect rate)
2. Send **50 events** with **3-4 failures** (6-8% rate)
3. Expected: WARNING alert

### Test 3: Verify Cooldown

1. Trigger an alert
2. Immediately send more failures
3. Expected: No new alert for 5 minutes

### Test 4: Insufficient Data

1. Send only **3 events** (below minimum of 5)
2. Expected: No alert (insufficient data)

---

## 📞 Support

For questions about alert logic:
- See `backend/app/detector.py` for implementation
- Check `backend/tests/test_detector.py` for test cases
- Review alert API: `GET /api/alerts` for active alerts

**Generated for SwitchOn Production Monitoring System**
