# English Abstract (draft)

**Title:** Development and Field Evaluation of an IoT System for Plant Care Support: Distinguishing Record Continuity from Measurement Validity

**Keywords:** IoT, Raspberry Pi, plant care support, data quality, capillary irrigation

## Abstract

This study developed an IoT system that supports plant care by continuously monitoring the growing environment, and evaluated it outdoors. The system combines two Raspberry Pi nodes with nutrient-solution temperature, illuminance, and water-level sensors, a cloud database (Supabase), web visualization, LINE/Slack notifications, and photo-based observation records. The evaluation distinguished record existence, sensor-value validity, and cloud-arrival latency, quantified against expected 5-minute slots. Between 13 June and 13 October 2026, the main node stored 35,407 records. Of 35,248 expected slots, 86.61% contained a record, but only 59.02% contained valid values from all three sensors. From 7 August to 9 September (32.9 days), both measures reached 100%. Outages included a 10.9-day gap from an authentication failure and a 39-hour interruption after the device toppled. After 9 September, records kept arriving in 99.86% of slots, while valid temperature and illuminance values fell to 0.01%, and the health score reported its maximum instead of flagging the missing sensors. Where outbox logs were retained, the median measurement-to-cloud latency was 0.92 s, and one duplicate record was caused by a retry. An uncalibrated moisture probe on a felt-wick irrigation structure was logged every 60 s for 17.3 days without missing samples. However, readings saturated near the ADC ceiling from 19 October, and irrigation-condition changes were not time-stamped, preventing comparison between conditions. These results show that continuous recording does not guarantee valid measurement. Future work includes detecting missing sensors, idempotent retransmission, logging experimental events, and calibrating the moisture probe.

(≈ 240 words)
