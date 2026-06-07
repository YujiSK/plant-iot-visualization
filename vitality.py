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
