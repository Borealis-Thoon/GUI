using System.Globalization;
using System.Reflection;
using System.Text.Json;
using Gral;

if (args.Length != 1 || !File.Exists(args[0]))
    throw new ArgumentException("Pass the path to the stock GRAMM.dll.");

CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo("de-DE");
var fixture = Path.Combine(Path.GetTempPath(), "gramm-scheduler-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(fixture);
string[] lines = Enumerable.Repeat("setting : 0 ! comment", 29).ToArray();
void Settings(int seconds)
{
    lines[3] = $"MODELLING TIME : {seconds} ! seconds";
    File.WriteAllLines(Path.Combine(fixture, "IIN.dat"), lines);
}
void Weather((int Stability, double Wind)[] rows)
{
    string[] met = rows.Select(row => string.Format(CultureInfo.InvariantCulture,
        "2; {0}; {1};0.5", row.Wind, row.Stability)).ToArray();
    File.WriteAllLines(Path.Combine(fixture, "meteopgt.all"), new[] { "10,0,0", "headers" }.Concat(met));
}
void Match(int first, int last, int k, int originalCount, params (int First, int Last)[] want)
{
    var got = GrammInstanceRanges.Create(fixture, first, last, k, originalCount);
    if (!got.SequenceEqual(want)) throw new Exception($"Ranges: {string.Join(",", got)}");
}
File.WriteAllLines(Path.Combine(fixture, "GRAMMin.dat"), new[] {"Version 17.01", "y", "0.2", "1,0", "no", "10"});
Settings(1800);
Match(1, 6, 3, 0, (1,2),(3,4),(5,6));
Match(3, 7, 3, 0, (3,4),(5,6),(7,7));
Match(5, 6, 8, 0, (5,5),(6,6));
Match(5, 5, 8, 0, (5,5));
Match(5, 9, 1, 9, (5,9));
Weather(new[] {(1,1.5),(2,1.5),(4,1.5),(4,1.5)});
Match(1, 4, 2, 4, (1,1),(2,4));
File.AppendAllText(Path.Combine(fixture, "meteopgt.all"), "invalid appended sentinel\n");
Match(1, 4, 2, 4, (1,1),(2,4));
lines[25] = "TRANSIENT : 1";
Settings(1800);
Match(1, 4, 2, 4, (1,2),(3,4));
lines[25] = "TRANSIENT : 0";
Settings(1);
Match(1, 4, 2, 4, (1,2),(3,4));
Settings(1800);
File.WriteAllLines(Path.Combine(fixture,"meteopgt.all"), new[] {"x", "x", "bad"});
Match(1, 4, 2, 4, (1,2),(3,4));
Weather(new[] {(1,1.5),(2,1.5),(3,1.5),(2,1.5),(3,1.5)});
Match(2, 5, 3, 5, (2,3),(4,4),(5,5));

var engine = Assembly.LoadFrom(args[0]).GetType("GRAMM_2001.Meteopgtall").GetMethod("Integrationtime");
long EngineWeight(int stability, double speed, int seconds)
{
    object[] parameters = {stability, speed, (double)seconds, 1, 0.0};
    engine.Invoke(null, parameters);
    return (long)Math.Round((double)parameters[4]*100);
}
long BruteForce(long[] w, int start, int workers)
{
    if (workers == 1) return w[start..].Sum();
    long best = long.MaxValue, total = 0;
    for (int i = start; i <= w.Length - workers; i++)
    {
        total += w[i];
        best = Math.Min(best, Math.Max(total, BruteForce(w, i+1, workers-1)));
    }
    return best;
}
var random = new Random(81233);
int plans = 0;
double[] speeds = {0.01,0.49,0.5,0.99,1,1.99,2,2.01,4};
foreach (int seconds in new[] {2, 1300, 3600, 7201, 100000000})
{
    Settings(seconds);
    for (int seed = 0; seed < 30; seed++)
    {
        var weather = Enumerable.Range(0,10).Select(_ => (random.Next(1,8), speeds[random.Next(speeds.Length)])).ToArray();
        Weather(weather);
        for (int first = 1; first <= 4; first++)
        {
            long[] weights = weather[(first-1)..].Select(row => EngineWeight(row.Item1,row.Item2,seconds)).ToArray();
            for (int request = 1; request <= 12; request++)
            {
                int workers = Math.Min(request,weights.Length);
                var ranges = GrammInstanceRanges.Create(fixture, first, 10, request, 10);
                long maximum = ranges.Max(range => weights[(range.First-first)..(range.Last-first+1)].Sum());
                var covered = ranges.SelectMany(range => Enumerable.Range(range.First,range.Last-range.First+1));
                if (ranges.Count != workers || !covered.SequenceEqual(Enumerable.Range(first, weights.Length)) ||
                    maximum != BruteForce(weights,0,workers))
                    throw new Exception($"Plan failed at {seconds}, {seed}, {first}, {request}");
                plans++;
            }
        }
    }
}
Console.WriteLine(JsonSerializer.Serialize(new { status = "pass", engineCheckedPlans = plans, targetedCases = 11 }));
