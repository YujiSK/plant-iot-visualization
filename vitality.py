from datetime import datetime
from typing import Optional


def score_temp(temperature: float) -> int:
    """Temperature score: optimal 24-28, acceptable 20-30, poor otherwise."""
    if 24 <= temperature <= 28:
        return 100
    if 20 <= temperature <= 30:
        return 70
    return 40


def score_humidity(humidity: float) -> int:
    """Humidity score: optimal 40-60, acceptable 35-70, poor otherwise."""
    if 40 <= humidity <= 60:
        return 100
    if 35 <= humidity <= 70:
        return 70
    return 40


def calculate_vitality(temperature: float, humidity: float) -> int:
    """Calculate vitality score: temp*0.6 + humidity*0.4."""
    return int(score_temp(temperature) * 0.6 + score_humidity(humidity) * 0.4)


def generate_message(temperature: float, humidity: float) -> str:
    """Generate status message based on temperature and humidity."""
    if humidity < 35:
        return "乾燥しています"
    if temperature > 30:
        return "温度が高めです"
    return "安定しています"


def score_solution_temperature(temperature: float) -> int:
    """Score basil root-zone temperature using conservative hydroponic bands."""
    if 22 <= temperature <= 26:
        return 100
    if 18 <= temperature <= 28:
        return 80
    if 15 <= temperature < 30:
        return 55
    if 10 <= temperature < 32:
        return 25
    return 10


def score_light_lux(lux: float) -> int:
    """Score instantaneous daylight lux as a rough proxy, not as PPFD or DLI."""
    if lux >= 10000:
        return 100
    if lux >= 5000:
        return 80
    if lux >= 2000:
        return 60
    if lux >= 500:
        return 35
    return 15


def is_core_daylight(
    observed_at: Optional[datetime],
    start_hour: int = 9,
    end_hour: int = 15,
) -> bool:
    """Return whether an instantaneous lux reading is suitable for evaluation."""
    if observed_at is None:
        return True
    return start_hour <= observed_at.hour < end_hour


def calculate_basil_vitality(
    *,
    temperature: Optional[float] = None,
    humidity: Optional[float] = None,
    solution_temperature: Optional[float] = None,
    light_lux: Optional[float] = None,
    water_status: Optional[str] = None,
    float_switch_triggered: Optional[bool] = None,
    observed_at: Optional[datetime] = None,
    light_start_hour: int = 9,
    light_end_hour: int = 15,
) -> tuple[int, str]:
    """Evaluate basil condition while keeping critical stresses non-compensatory."""
    components = []
    messages = []

    if temperature is not None:
        components.append((score_temp(temperature), 20))
        if temperature > 30:
            messages.append("気温が高く蒸散ストレスに注意が必要です")
        elif temperature < 15:
            messages.append("気温が低く低温ストレスに注意が必要です")

    if humidity is not None:
        components.append((score_humidity(humidity), 10))
        if humidity < 35:
            messages.append("空気が乾燥し蒸散が増えやすい状態です")
        elif humidity > 80:
            messages.append("湿度が高く病害リスクに注意が必要です")

    if solution_temperature is not None:
        components.append((score_solution_temperature(solution_temperature), 30))
        if solution_temperature >= 30:
            messages.append("養液が高温で根の酸素不足リスクが高まっています")
        elif solution_temperature > 28:
            messages.append("養液温度が高めです")
        elif solution_temperature < 15:
            messages.append("養液が低温で根の吸水・生育低下に注意が必要です")
        elif solution_temperature < 18:
            messages.append("養液温度が低めです")

    normalized_water_status = water_status
    if float_switch_triggered is not None:
        normalized_water_status = "low_water" if float_switch_triggered else "water_ok"

    if normalized_water_status is not None:
        water_scores = {
            "low_water": 0,
            "dry": 0,
            "transition": 45,
            "wet": 90,
            "enough_water": 100,
            "water_ok": 100,
        }
        components.append((water_scores.get(normalized_water_status, 50), 35))
        if normalized_water_status in {"low_water", "dry"}:
            messages.append("水位低下を検出しました。根への給水を最優先で確認してください")
        elif normalized_water_status == "transition":
            messages.append("水位が境界域です。低下傾向を確認してください")
    elif float_switch_triggered is None:
        messages.append("水位を確認できないため判定の信頼度が低下しています")

    evaluate_light = light_lux is not None and is_core_daylight(
        observed_at,
        light_start_hour,
        light_end_hour,
    )
    if evaluate_light:
        components.append((score_light_lux(light_lux), 15))
        if light_lux < 2000:
            messages.append("日中の照度が低く、光量不足が続く可能性があります")
        elif light_lux < 5000:
            messages.append("日中の照度がやや低めです")

    if not components:
        return 0, "センサーデータがなく状態を判定できません"

    total_weight = sum(weight for _, weight in components)
    score = round(sum(value * weight for value, weight in components) / total_weight)

    low_water = normalized_water_status in {"low_water", "dry"}
    severe_solution_heat = (
        solution_temperature is not None and solution_temperature >= 30
    )
    severe_solution_cold = (
        solution_temperature is not None and solution_temperature < 15
    )

    if low_water:
        score = min(score, 25)
    if severe_solution_heat:
        score = min(score, 55)
    if severe_solution_cold:
        score = min(score, 40)
    if low_water and (severe_solution_heat or severe_solution_cold):
        score = min(score, 15)
        messages.insert(0, "水位と養液温度の複合ストレスが発生しています")
    elif (
        severe_solution_heat
        and evaluate_light
        and light_lux is not None
        and light_lux >= 10000
    ):
        score = min(score, 45)
        messages.insert(0, "高温の養液と強い日射が重なっています")

    if normalized_water_status is None:
        score = min(score, 70)

    return max(0, min(100, score)), (
        " / ".join(messages) if messages else "安定しています"
    )
