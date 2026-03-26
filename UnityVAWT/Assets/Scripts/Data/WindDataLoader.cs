using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEngine;
using UnityEngine.Networking;

namespace CDO.VAWT.Unity
{
    [Serializable]
    public struct WindSample
    {
        public int HourOfYear;
        public string Season;
        public float WindSpeed15mMs;
        public float WindDirection10mDeg;
        public float AirDensityKgm3;
    }

    public class WindDataLoader : MonoBehaviour
    {
        [SerializeField] private string csvFileName = "CDO_wind_2023_hourly.csv";
        [SerializeField] private bool autoLoadOnStart = true;

        private readonly List<WindSample> samples = new List<WindSample>(8760);

        public event Action<IReadOnlyList<WindSample>> DataLoaded;
        public event Action<string> DataLoadFailed;

        public IReadOnlyList<WindSample> Samples => samples;
        public bool IsLoaded { get; private set; }

        private void Start()
        {
            if (autoLoadOnStart)
            {
                StartCoroutine(LoadCsvRoutine());
            }
        }

        public void Reload()
        {
            StartCoroutine(LoadCsvRoutine());
        }

        private IEnumerator LoadCsvRoutine()
        {
            IsLoaded = false;
            samples.Clear();

            string uri = BuildStreamingAssetsUri(csvFileName);
            using (UnityWebRequest request = UnityWebRequest.Get(uri))
            {
                yield return request.SendWebRequest();

                if (request.result != UnityWebRequest.Result.Success)
                {
                    string error = $"Failed to load wind CSV from {uri}: {request.error}";
                    Debug.LogError(error);
                    DataLoadFailed?.Invoke(error);
                    yield break;
                }

                try
                {
                    ParseCsv(request.downloadHandler.text);
                    IsLoaded = true;
                    DataLoaded?.Invoke(samples);
                    Debug.Log($"WindDataLoader loaded {samples.Count} samples.");
                }
                catch (Exception ex)
                {
                    Debug.LogError(ex);
                    DataLoadFailed?.Invoke(ex.Message);
                }
            }
        }

        private static string BuildStreamingAssetsUri(string fileName)
        {
            string combinedPath = Path.Combine(Application.streamingAssetsPath, fileName);
            if (combinedPath.StartsWith("http", StringComparison.OrdinalIgnoreCase))
            {
                return combinedPath;
            }

            return $"file://{combinedPath.Replace("\\", "/")}";
        }

        private void ParseCsv(string csvText)
        {
            string[] lines = csvText.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);
            if (lines.Length < 2)
            {
                throw new InvalidDataException("CSV is empty or missing data rows.");
            }

            string[] headers = lines[0].Split(',');
            Dictionary<string, int> indexByName = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            for (int i = 0; i < headers.Length; i++)
            {
                indexByName[headers[i].Trim()] = i;
            }

            string[] required = {
                "hour_of_year",
                "season",
                "wind_speed_15m_ms",
                "wind_direction_10m_deg",
                "air_density_kgm3"
            };

            foreach (string requiredColumn in required)
            {
                if (!indexByName.ContainsKey(requiredColumn))
                {
                    throw new InvalidDataException($"Missing required column: {requiredColumn}");
                }
            }

            for (int lineIndex = 1; lineIndex < lines.Length; lineIndex++)
            {
                string[] values = lines[lineIndex].Split(',');
                if (values.Length < headers.Length)
                {
                    continue;
                }

                WindSample sample = new WindSample
                {
                    HourOfYear = ParseInt(values[indexByName["hour_of_year"]]),
                    Season = values[indexByName["season"]].Trim(),
                    WindSpeed15mMs = ParseFloat(values[indexByName["wind_speed_15m_ms"]]),
                    WindDirection10mDeg = ParseFloat(values[indexByName["wind_direction_10m_deg"]]),
                    AirDensityKgm3 = ParseFloat(values[indexByName["air_density_kgm3"]]),
                };

                samples.Add(sample);
            }
        }

        private static int ParseInt(string value)
        {
            return int.Parse(value.Trim(), CultureInfo.InvariantCulture);
        }

        private static float ParseFloat(string value)
        {
            return float.Parse(value.Trim(), CultureInfo.InvariantCulture);
        }
    }
}
