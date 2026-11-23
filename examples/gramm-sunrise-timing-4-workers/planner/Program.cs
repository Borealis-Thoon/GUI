using System;
using System.Linq;
using System.Text.Json;
using Gral;

var ranges = GrammInstanceRanges.Create(args[0], 1, 48, 4, 48);
Console.WriteLine(JsonSerializer.Serialize(ranges.Select(r => new[] { r.First, r.Last })));
