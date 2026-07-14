import numpy as np
import pandas as pd

from scipy.stats import skew, kurtosis


def _compute_mean(data: np.ndarray) -> float:
    return float(np.mean(data))


def _compute_std(data: np.ndarray) -> float:
    return float(np.std(data))


def _compute_min(data: np.ndarray) -> float:
    return float(np.min(data))


def _compute_max(data: np.ndarray) -> float:
    return float(np.max(data))


def _compute_p05(data: np.ndarray) -> float:
    return float(np.percentile(data, 5))


def _compute_p95(data: np.ndarray) -> float:
    return float(np.percentile(data, 95))


def _compute_rms(data: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(data))))


def _compute_skewness(data: np.ndarray) -> float:
    return float(skew(data))


def _compute_kurtosis(data: np.ndarray) -> float:
    return float(kurtosis(data))


def _compute_magnitude(data: np.ndarray) -> np.ndarray:
    return np.linalg.norm(data, axis=1)


def _compute_jerk(
        data: np.ndarray, 
        sample_rate_hz: float = 1000.0
) -> np.ndarray:
    # IMU sampling rate is 1KHz, so dt = 0.001s
    dt = 1.0 / sample_rate_hz
    jerk = np.diff(data, axis=0) / dt
    return _compute_magnitude(jerk)


def _compute_pearson_correlation(
        data1: np.ndarray, 
        data2: np.ndarray
) -> float:
    if len(data1) != len(data2):
        raise ValueError("Input arrays must have the same length.")
    correlation = float(np.corrcoef(data1, data2)[0, 1])
    return float(np.clip(correlation, -1.0, 1.0))  # Ensure the correlation is within [-1, 1]


def _compute_total_angular_displacement_deg(
    gyro_data: np.ndarray, 
    sample_rate_hz: float = 1000.0
) -> float:
    # Integrate gyro data to get total angular displacement in degrees
    # Assuming data is in deg/s and sampled at 1KHz
    magnitude = _compute_magnitude(gyro_data)
    dt = 1.0 / sample_rate_hz
    return float(np.sum(magnitude * dt))


def _compute_zero_crossing(data: np.ndarray) -> int:
    centered = data - _compute_mean(data)
    signs = np.sign(centered)
    signs[signs == 0] = 1  # Treat zeros as positive to avoid false crossings
    return int(np.count_nonzero(np.diff(signs)))


def compute_event_statistics(df: pd.DataFrame) -> dict:

    acc_x = df.acc_x.to_numpy()
    acc_y = df.acc_y.to_numpy()
    acc_z = df.acc_z.to_numpy()
    acc_3d = np.column_stack((acc_x, acc_y, acc_z))
    
    gyro_x = df.gyro_x.to_numpy()
    gyro_y = df.gyro_y.to_numpy()
    gyro_z = df.gyro_z.to_numpy()
    gyro_3d = np.column_stack((gyro_x, gyro_y, gyro_z))
    
    lat = df.lat.to_numpy()
    lon = df.lon.to_numpy()
    hdop = df.hdop.to_numpy()
    speed = df.speed.to_numpy()
    gps_fix = df.gps_fix.to_numpy()
    
    algo_enabled = df.algo_enabled.to_numpy()
    algo_ignited = df.algo_ignited.to_numpy()
    mask = (algo_enabled == 1) & (algo_ignited == 1)
    idx = np.flatnonzero(mask)[0] if mask.any() else None

    return {
        # Accelerometer statistics (m/s²)
        "acc_x_mean": _compute_mean(acc_x),
        "acc_y_mean": _compute_mean(acc_y),
        "acc_z_mean": _compute_mean(acc_z),
        "acc_x_std": _compute_std(acc_x),
        "acc_y_std": _compute_std(acc_y),
        "acc_z_std": _compute_std(acc_z),
        "acc_x_min": _compute_min(acc_x),
        "acc_y_min": _compute_min(acc_y),
        "acc_z_min": _compute_min(acc_z),
        "acc_x_max": _compute_max(acc_x),
        "acc_y_max": _compute_max(acc_y),
        "acc_z_max": _compute_max(acc_z),
        "acc_x_p05": _compute_p05(acc_x),
        "acc_y_p05": _compute_p05(acc_y),
        "acc_z_p05": _compute_p05(acc_z),
        "acc_x_p95": _compute_p95(acc_x),
        "acc_y_p95": _compute_p95(acc_y),
        "acc_z_p95": _compute_p95(acc_z),
        "acc_x_rms": _compute_rms(acc_x),
        "acc_y_rms": _compute_rms(acc_y),
        "acc_z_rms": _compute_rms(acc_z),
        "acc_x_skew": _compute_skewness(acc_x),
        "acc_y_skew": _compute_skewness(acc_y),
        "acc_z_skew": _compute_skewness(acc_z),
        "acc_x_kurtosis": _compute_kurtosis(acc_x),
        "acc_y_kurtosis": _compute_kurtosis(acc_y),
        "acc_z_kurtosis": _compute_kurtosis(acc_z),
        "acc_x_zero_crossings": _compute_zero_crossing(acc_x),
        "acc_y_zero_crossings": _compute_zero_crossing(acc_y),
        "acc_z_zero_crossings": _compute_zero_crossing(acc_z),
        # Gyroscope statistics (deg/s)
        "gyro_x_mean": _compute_mean(gyro_x),
        "gyro_y_mean": _compute_mean(gyro_y),
        "gyro_z_mean": _compute_mean(gyro_z),
        "gyro_x_std": _compute_std(gyro_x),
        "gyro_y_std": _compute_std(gyro_y),
        "gyro_z_std": _compute_std(gyro_z),
        "gyro_x_min": _compute_min(gyro_x),
        "gyro_y_min": _compute_min(gyro_y),
        "gyro_z_min": _compute_min(gyro_z),
        "gyro_x_max": _compute_max(gyro_x),
        "gyro_y_max": _compute_max(gyro_y),
        "gyro_z_max": _compute_max(gyro_z),
        "gyro_x_p05": _compute_p05(gyro_x),
        "gyro_y_p05": _compute_p05(gyro_y),
        "gyro_z_p05": _compute_p05(gyro_z),
        "gyro_x_p95": _compute_p95(gyro_x),
        "gyro_y_p95": _compute_p95(gyro_y),
        "gyro_z_p95": _compute_p95(gyro_z),
        "gyro_x_rms": _compute_rms(gyro_x),
        "gyro_y_rms": _compute_rms(gyro_y),
        "gyro_z_rms": _compute_rms(gyro_z),
        "gyro_x_skew": _compute_skewness(gyro_x),
        "gyro_y_skew": _compute_skewness(gyro_y),
        "gyro_z_skew": _compute_skewness(gyro_z),
        "gyro_x_kurtosis": _compute_kurtosis(gyro_x),
        "gyro_y_kurtosis": _compute_kurtosis(gyro_y),
        "gyro_z_kurtosis": _compute_kurtosis(gyro_z),
        "gyro_x_zero_crossings": _compute_zero_crossing(gyro_x),
        "gyro_y_zero_crossings": _compute_zero_crossing(gyro_y),
        "gyro_z_zero_crossings": _compute_zero_crossing(gyro_z),
        # Accelerometer magnitudes
        "acc_magnitude_mean": _compute_mean(_compute_magnitude(acc_3d)),
        "acc_magnitude_std": _compute_std(_compute_magnitude(acc_3d)),
        "acc_magnitude_max": _compute_max(_compute_magnitude(acc_3d)),
        "acc_magnitude_p05": _compute_p05(_compute_magnitude(acc_3d)),
        "acc_magnitude_p95": _compute_p95(_compute_magnitude(acc_3d)),
        "acc_magnitude_skew": _compute_skewness(_compute_magnitude(acc_3d)),
        "acc_magnitude_kurtosis": _compute_kurtosis(_compute_magnitude(acc_3d)),
        # Gyroscope magnitudes
        "gyro_magnitude_mean": _compute_mean(_compute_magnitude(gyro_3d)),
        "gyro_magnitude_std": _compute_std(_compute_magnitude(gyro_3d)),
        "gyro_magnitude_max": _compute_max(_compute_magnitude(gyro_3d)),
        "gyro_magnitude_p05": _compute_p05(_compute_magnitude(gyro_3d)),
        "gyro_magnitude_p95": _compute_p95(_compute_magnitude(gyro_3d)),
        "gyro_magnitude_skew": _compute_skewness(_compute_magnitude(gyro_3d)),
        "gyro_magnitude_kurtosis": _compute_kurtosis(_compute_magnitude(gyro_3d)),
        # Accelerometer jerk
        "acc_jerk_mean": _compute_mean(_compute_jerk(acc_3d)),
        "acc_jerk_std": _compute_std(_compute_jerk(acc_3d)),
        "acc_jerk_p95": _compute_p95(_compute_jerk(acc_3d)),
        # Gyroscope jerk
        "gyro_jerk_mean": _compute_mean(_compute_jerk(gyro_3d)),
        "gyro_jerk_std": _compute_std(_compute_jerk(gyro_3d)),
        "gyro_jerk_p95": _compute_p95(_compute_jerk(gyro_3d)),
        # Total angular displacement
        "total_angular_displacement_deg": _compute_total_angular_displacement_deg(gyro_3d),
        # Inter-axis correlations
        "acc_xy_correlation": _compute_pearson_correlation(acc_x, acc_y),
        "acc_xz_correlation": _compute_pearson_correlation(acc_x, acc_z),
        "acc_yz_correlation": _compute_pearson_correlation(acc_y, acc_z),
        "gyro_xy_correlation": _compute_pearson_correlation(gyro_x, gyro_y),
        "gyro_xz_correlation": _compute_pearson_correlation(gyro_x, gyro_z),
        "gyro_yz_correlation": _compute_pearson_correlation(gyro_y, gyro_z),
        # GPS
        "lat_mean": _compute_mean(lat),
        "lon_mean": _compute_mean(lon),
        "hdop_mean": _compute_mean(hdop),
        # Speed
        "speed_max": _compute_max(speed),
        "speed_at_start": next((float(x) for x in speed if x > 0), 0.0),
        "speed_at_ignition": float(speed[idx]) if idx is not None else 0.0,
        "speed_at_end": next((float(x) for x in reversed(speed) if x > 0), 0.0),
        # Quality metrics
        "n_samples": len(df),
        "gps_fix_ratio": _compute_mean(gps_fix),
        "algo_enabled_start": bool(algo_enabled[0]),
        "algo_enabled_end": bool(algo_enabled[-1]),
        "algo_enabled_ratio": _compute_mean(algo_enabled),
        "algo_ignited": True if idx is not None else False,
    }
