# Abstract (English)

## Title

**Development of an IoT System for Plant Management Support and Field Evaluation of Recording Continuity and Measurement Validity**

## Keywords

IoT; plant management support; field operation; data quality; moisture sensing

## Abstract

This study developed a Raspberry Pi–based IoT system to support plant management and evaluated it in real-world operation. The system measures nutrient-solution temperature, illuminance, and water level every five minutes and sends them to Supabase. It also provides a retrying local outbox, a web dashboard, LINE/Slack notifications, and photo-based observation logging. The evaluation separated three properties of the data: whether a record exists, whether its values are valid, and whether it reached the cloud. Each was quantified against expected five-minute slots. Across 35,407 records collected outdoors from 13 June to 13 October 2026, 86.61% of slots contained a record, but only 59.02% held valid values for all three sensors. An 11-day post-recovery window reached 99.91% on both measures. In the final 34 days, however, records filled 99.86% of slots while valid temperature and illuminance were present in only 0.01%. The values were already missing on the device, yet the composite health score reported 100 ("stable") and heartbeat monitoring raised no alarm. All 10,117 queued records reached the cloud (median delay 1.30 s), although one lost response caused a duplicate. A moisture probe in a felt-wick substrate logged uncalibrated ADC values every 60 s for 17 days without gaps. However, the readings reached the ADC ceiling within six days, and no condition changes were logged, so wick-count and watering effects could not be assessed. Recording continuity and measurement validity can therefore diverge sharply in field operation, and monitoring must verify value validity, not just data arrival.
