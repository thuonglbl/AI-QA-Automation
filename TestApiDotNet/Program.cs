using System.Text;
using System.Text.Json;

// Load config
var configPath = Path.Combine(Directory.GetCurrentDirectory(), "..", "config.yaml");
if (!File.Exists(configPath))
    configPath = Path.Combine(Directory.GetCurrentDirectory(), "config.yaml");

var configLines = File.ReadAllLines(configPath);
var config = new Dictionary<string, string>();
foreach (var line in configLines)
{
    var trimmed = line.Trim();
    if (trimmed.Contains(':') && !trimmed.StartsWith('#') && !trimmed.StartsWith("ai_server"))
    {
        var parts = trimmed.Split(':', 2);
        config[parts[0].Trim()] = parts[1].Trim().Trim('"');
    }
}

var baseUrl = config["base_url"].TrimEnd('/');
var apiKey = Environment.GetEnvironmentVariable("AI_API_KEY") ?? config["api_key"];
var model = config["model"];

// Use local proxy (Python h2 proxy on port 8000)
var proxyUrl = "http://localhost:8000";

Console.WriteLine($"Server: {baseUrl} (via local h2 proxy)");
Console.WriteLine($"Model:  {model}");

using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(120) };
client.DefaultRequestHeaders.Add("Authorization", $"Bearer {apiKey}");

// Verify proxy is running
try
{
    var test = await client.GetAsync($"{proxyUrl}/health");
    Console.WriteLine($"Proxy connected. Server health: {(int)test.StatusCode}");
}
catch
{
    Console.WriteLine("ERROR: Local proxy not running. Start it first:");
    Console.WriteLine("  python h2_proxy.py");
    return;
}

// Chat loop
var messages = new List<object>();
Console.WriteLine("\nChat started. Type 'exit' to quit.");
Console.WriteLine(new string('-', 40));

while (true)
{
    Console.Write("\nYou: ");
    var input = Console.ReadLine();
    if (string.IsNullOrWhiteSpace(input) || input.Trim().Equals("exit", StringComparison.OrdinalIgnoreCase))
    {
        Console.WriteLine("Bye!");
        break;
    }

    messages.Add(new { role = "user", content = input });
    var payload = JsonSerializer.Serialize(new { model, messages });
    var content = new StringContent(payload, Encoding.UTF8, "application/json");

    try
    {
        var response = await client.PostAsync($"{proxyUrl}/v1/chat/completions", content);

        if (!response.IsSuccessStatusCode)
        {
            var err = await response.Content.ReadAsStringAsync();
            Console.WriteLine($"[Error] HTTP {(int)response.StatusCode}: {err[..Math.Min(err.Length, 200)]}");
            messages.RemoveAt(messages.Count - 1);
            continue;
        }

        var body = await response.Content.ReadAsStringAsync();
        var json = JsonSerializer.Deserialize<JsonElement>(body);
        var reply = json.GetProperty("choices")[0]
                        .GetProperty("message")
                        .GetProperty("content")
                        .GetString()?.Trim();

        Console.WriteLine($"\nAI: {reply}");
        messages.Add(new { role = "assistant", content = reply });
    }
    catch (Exception ex)
    {
        Console.WriteLine($"[Error] {ex.Message}");
        messages.RemoveAt(messages.Count - 1);
    }
}
