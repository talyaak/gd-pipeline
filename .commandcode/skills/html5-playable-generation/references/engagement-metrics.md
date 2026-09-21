# Engagement and Completion Metrics for HTML5 Playables

## Overview
Engagement duration and completion rate metrics provide quantitative measures of playable ad effectiveness, correlating with user retention and conversion rates in UA campaigns.

## Metrics Definitions

### Engagement Duration
- **Definition**: Total time (in milliseconds) the game spends in an active playable state after initial user interaction
- **Active Play States**: States where core gameplay mechanics are accessible (e.g., 'Play', 'GameScene', 'Level')
- **Measurement**: Tracked from first meaningful interaction until exit from active state or observation period ends
- **Unit**: Milliseconds (integer)
- **Value Range**: 0 to observation period max (typically 20,000ms)
- **Null Value**: Indicates measurement failed or no engagement detected

### Completion Rate
- **Definition**: Fraction of target session completed (0.0 to 1.0)
- **Calculation Methods**:
  1. **Win State Detection**: If win/victory state is reached → 1.0
  2. **Engagement Time Ratio**: (engagement_duration_ms / target_session_ms) capped at 1.0
  3. **Fallback**: 0.0 if no engagement detected
- **Target Session**: Typically 30 seconds (30,000ms) for HTML5 playable ads
- **Value Range**: 0.0 to 1.0 (float)

## Implementation Details

### Observation Period
- Extend test execution beyond input sequence to 20 seconds post-interaction
- Sample game state every 500ms during observation
- Use page.evaluate() to read game state from window.__GAME__

### Game State Detection
The implementation detects active play states through multiple heuristics:

1. **Explicit State Property**: `game.state` if available
2. **Scene-Based Detection**: 
   - Active scenes with keys containing: 'play', 'game', 'level'
   - Menu scenes: 'menu', 'main', 'start' 
   - Game over scenes: 'gameover', 'game over', 'over'
   - Win scenes: 'win', 'won', 'victory', 'success'
3. **Registry-Based Signals**:
   - `game.registry.get('score') > 0` indicates active play
   - `game.registry.get('gameOver') === true` indicates session end

### State Transition Handling
- Engagement starts when first active play state is detected
- Engagement ends when transitioning out of active state
- Win states immediately set completion_rate = 1.0
- Game over states after engagement count as completed sessions
- Extended observation captures post-game-over screens (replay buttons, etc.)

## Validation Criteria

### Test Expectations
- Engagement duration should be >= 0ms when measured
- Completion rate should be between 0.0 and 1.0 inclusive
- At least one of the metrics should be non-trivial for viable playables:
  * Engagement duration > 1000ms (1 second of play)
  * OR completion rate > 0.1 (10% of target session)

### Edge Cases
- **Immediate Game Over**: Engagement duration may be 0 if gameOver on load
- **Win on Load**: Completion rate = 1.0, engagement duration measures time to win
- **No User Interaction**: Both metrics should be 0/null (input detection fails first)
- **Technical Errors**: Metrics collection failures should not fail validation (graceful degradation)

## Usage in Pipeline

### Execution Report Schema
The metrics are stored in the ExecutionReport object:
```python
engagement_duration_ms: Optional[int] = Field(
    default=None,
    description="Measured time the game remained in an active playable state (e.g., PLAYING state) before completing or stopping. None if not measured."
)
completion_rate: Optional[float] = Field(
    default=None,
    description="Fraction of target session completed (0.0 to 1.0). For example, 0.75 means 75% of the target session was completed. None if not measured."
)
```

### Codegen Requirements
To enable accurate metric collection, games should:
1. Expose Phaser.Game instance as `window.__GAME__`
2. Initialize score registry: `game.registry.set('score', 0)`
3. Initialize game state tracking: `game.registry.set('gameOver', false)`
4. Update score or state during active gameplay
5. Set win/lose states appropriately in registry or scene transitions

## Correlation with UA Performance
Industry benchmarks show:
- Engagement duration > 15s correlates with 2-3x higher conversion rates
- Completion rate > 0.8 indicates strong retention potential
- These metrics predict post-install performance better than click-through rates alone