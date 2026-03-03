namespace HydraWorker;

public class Worker : BackgroundService
{
    private const int HeartbeatIntervalMs = 1000;

    private readonly ILogger<Worker> _logger;

    public Worker(ILogger<Worker> logger)
    {
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            if (_logger.IsEnabled(LogLevel.Information))
            {
                _logger.LogInformation("Worker running at: {timestamp}", DateTimeOffset.UtcNow);
            }
            await Task.Delay(HeartbeatIntervalMs, stoppingToken);
        }
    }
}
