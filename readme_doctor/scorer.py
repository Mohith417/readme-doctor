def parse_score(analysis_text):
    """Extract the numeric score from the AI analysis"""
    try:
        for line in analysis_text.split('\n'):
            if line.startswith('SCORE:'):
                score = line.replace('SCORE:', '').strip()
                return int(''.join(filter(str.isdigit, score)))
    except:
        return 0
    return 0

def get_grade(score):
    """Convert numeric score to a letter grade"""
    if score >= 90:
        return "A", "Excellent README!"
    elif score >= 75:
        return "B", "Good README, minor improvements needed"
    elif score >= 60:
        return "C", "Average README, needs work"
    elif score >= 40:
        return "D", "Poor README, significant improvements needed"
    else:
        return "F", "Very poor README, needs complete rewrite"