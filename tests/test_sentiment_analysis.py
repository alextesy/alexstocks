"""Tests for sentiment analysis functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from app.services.sentiment import SentimentService
from app.services.llm_sentiment import LLMSentimentService
from app.services.hybrid_sentiment import HybridSentimentService
from app.db.models import Article
from faker import Faker

fake = Faker()


class TestSentimentService:
    """Test VADER sentiment analysis service."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch('vaderSentiment.vaderSentiment.SentimentIntensityAnalyzer'):
            self.service = SentimentService()

    def test_initialization(self):
        """Test SentimentService initialization."""
        assert self.service._analyzer is not None

    def test_analyze_sentiment_positive(self):
        """Test positive sentiment analysis."""
        service = SentimentService()
        result = service.analyze_sentiment("I love this stock! It's amazing!")
        
        # VADER should return a positive sentiment score
        assert result > 0.0
        assert result <= 1.0

    def test_analyze_sentiment_negative(self):
        """Test negative sentiment analysis."""
        service = SentimentService()
        result = service.analyze_sentiment("This stock is terrible! I hate it!")
        
        # VADER should return a negative sentiment score
        assert result < 0.0
        assert result >= -1.0

    def test_analyze_sentiment_neutral(self):
        """Test neutral sentiment analysis."""
        service = SentimentService()
        result = service.analyze_sentiment("The stock price is $100.")
        
        # VADER should return a neutral sentiment score (close to 0)
        assert -0.1 <= result <= 0.1

    def test_analyze_sentiment_empty_text(self):
        """Test sentiment analysis with empty text."""
        with pytest.raises(ValueError, match="Text cannot be empty or None"):
            self.service.analyze_sentiment("")

    def test_analyze_sentiment_none_text(self):
        """Test sentiment analysis with None text."""
        with pytest.raises(ValueError, match="Text cannot be empty or None"):
            self.service.analyze_sentiment(None)

    def test_analyze_sentiment_whitespace_only(self):
        """Test sentiment analysis with whitespace-only text."""
        with pytest.raises(ValueError, match="Text cannot be empty or None"):
            self.service.analyze_sentiment("   \n\t   ")

    def test_get_sentiment_label_positive(self):
        """Test sentiment label for positive score."""
        assert self.service.get_sentiment_label(0.1) == "Positive"
        assert self.service.get_sentiment_label(0.5) == "Positive"
        assert self.service.get_sentiment_label(1.0) == "Positive"

    def test_get_sentiment_label_negative(self):
        """Test sentiment label for negative score."""
        assert self.service.get_sentiment_label(-0.1) == "Negative"
        assert self.service.get_sentiment_label(-0.5) == "Negative"
        assert self.service.get_sentiment_label(-1.0) == "Negative"

    def test_get_sentiment_label_neutral(self):
        """Test sentiment label for neutral score."""
        assert self.service.get_sentiment_label(0.0) == "Neutral"
        assert self.service.get_sentiment_label(0.04) == "Neutral"
        assert self.service.get_sentiment_label(-0.04) == "Neutral"

    def test_analyze_with_label(self):
        """Test analyze_with_label method."""
        with patch.object(self.service, 'analyze_sentiment', return_value=0.7):
            score, label = self.service.analyze_with_label("Great stock!")
            
            assert score == 0.7
            assert label == "Positive"


class TestLLMSentimentService:
    """Test LLM-based sentiment analysis service."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_pipeline = Mock()
        self.mock_pipeline.return_value = [
            [
                {'label': 'positive', 'score': 0.8},
                {'label': 'negative', 'score': 0.1},
                {'label': 'neutral', 'score': 0.1}
            ]
        ]

    @patch('app.services.llm_sentiment.TRANSFORMERS_AVAILABLE', True)
    @patch('app.services.llm_sentiment.pipeline')
    def test_initialization_success(self, mock_pipeline):
        """Test successful LLM service initialization."""
        mock_pipeline.return_value = self.mock_pipeline
        
        service = LLMSentimentService(model_name="test-model", use_gpu=False)
        
        assert service.model_name == "test-model"
        assert service.use_gpu is False
        assert service._device == -1

    @patch('app.services.llm_sentiment.TRANSFORMERS_AVAILABLE', False)
    def test_initialization_no_transformers(self):
        """Test initialization when transformers is not available."""
        with pytest.raises(RuntimeError, match="Transformers library not available"):
            LLMSentimentService()

    @patch('app.services.llm_sentiment.TRANSFORMERS_AVAILABLE', True)
    @patch('app.services.llm_sentiment.pipeline')
    def test_analyze_sentiment_positive(self, mock_pipeline):
        """Test positive sentiment analysis with LLM."""
        # Mock the pipeline to return positive sentiment
        mock_pipeline.return_value = Mock(return_value=[
            [
                {'label': 'positive', 'score': 0.8},
                {'label': 'negative', 'score': 0.1},
                {'label': 'neutral', 'score': 0.1}
            ]
        ])
        
        service = LLMSentimentService()
        result = service.analyze_sentiment("I love this stock! It's amazing!")
        
        assert result == 0.7  # positive - negative = 0.8 - 0.1

    @patch('app.services.llm_sentiment.TRANSFORMERS_AVAILABLE', True)
    @patch('app.services.llm_sentiment.pipeline')
    def test_analyze_sentiment_negative(self, mock_pipeline):
        """Test negative sentiment analysis with LLM."""
        mock_pipeline.return_value = Mock(return_value=[
            [
                {'label': 'positive', 'score': 0.1},
                {'label': 'negative', 'score': 0.8},
                {'label': 'neutral', 'score': 0.1}
            ]
        ])
        
        service = LLMSentimentService()
        result = service.analyze_sentiment("This stock is terrible!")
        
        assert result == -0.7  # positive - negative = 0.1 - 0.8

    @patch('app.services.llm_sentiment.TRANSFORMERS_AVAILABLE', True)
    @patch('app.services.llm_sentiment.pipeline')
    def test_analyze_sentiment_roberta_format(self, mock_pipeline):
        """Test sentiment analysis with RoBERTa format."""
        mock_pipeline.return_value = Mock(return_value=[
            [
                {'label': 'label_0', 'score': 0.1},  # negative
                {'label': 'label_1', 'score': 0.2},  # neutral
                {'label': 'label_2', 'score': 0.7}   # positive
            ]
        ])
        
        service = LLMSentimentService()
        result = service.analyze_sentiment("Great stock!")
        
        assert result == 0.6  # positive - negative = 0.7 - 0.1

    @patch('app.services.llm_sentiment.TRANSFORMERS_AVAILABLE', True)
    @patch('app.services.llm_sentiment.pipeline')
    def test_analyze_sentiment_text_truncation(self, mock_pipeline):
        """Test text truncation for long inputs."""
        mock_pipeline.return_value = self.mock_pipeline
        
        service = LLMSentimentService()
        long_text = "A" * 3000  # Longer than 2000 char limit
        
        result = service.analyze_sentiment(long_text)
        
        # Should call with truncated text
        mock_pipeline.return_value.assert_called_once()
        call_args = mock_pipeline.return_value.call_args[0][0]
        assert len(call_args) <= 2003  # 2000 + "..."

    def test_analyze_sentiment_empty_text(self):
        """Test LLM sentiment analysis with empty text."""
        with patch('app.services.llm_sentiment.TRANSFORMERS_AVAILABLE', True):
            service = LLMSentimentService()
            
            with pytest.raises(ValueError, match="Text cannot be empty or None"):
                service.analyze_sentiment("")

    def test_get_sentiment_label(self):
        """Test sentiment label conversion."""
        with patch('app.services.llm_sentiment.TRANSFORMERS_AVAILABLE', True):
            service = LLMSentimentService()
            
            assert service.get_sentiment_label(0.1) == "Positive"
            assert service.get_sentiment_label(-0.1) == "Negative"
            assert service.get_sentiment_label(0.05) == "Neutral"

    def test_get_model_info(self):
        """Test model information retrieval."""
        with patch('app.services.llm_sentiment.TRANSFORMERS_AVAILABLE', True):
            service = LLMSentimentService(model_name="test-model", use_gpu=True)
            
            info = service.get_model_info()
            
            assert info["model_name"] == "test-model"
            assert info["use_gpu"] is True
            assert info["device"] == 0
            assert info["is_loaded"] is False
            assert info["transformers_available"] is True


class TestHybridSentimentService:
    """Test hybrid sentiment analysis service."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_vader_service = Mock()
        self.mock_llm_service = Mock()

    def test_initialization_dual_model_strategy(self):
        """Test initialization with dual model strategy."""
        with patch('app.services.hybrid_sentiment.get_llm_sentiment_service', return_value=self.mock_llm_service), \
             patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            
            service = HybridSentimentService(
                use_llm=True,
                dual_model_strategy=True,
                fallback_to_vader=True
            )
            
            assert service.dual_model_strategy is True
            assert service._llm_service == self.mock_llm_service
            assert service._vader_service == self.mock_vader_service

    def test_initialization_llm_only(self):
        """Test initialization with LLM only."""
        with patch('app.services.hybrid_sentiment.get_llm_sentiment_service', return_value=self.mock_llm_service):
            service = HybridSentimentService(
                use_llm=True,
                dual_model_strategy=False,
                fallback_to_vader=False
            )
            
            assert service.use_llm is True
            assert service.dual_model_strategy is False
            assert service._llm_service == self.mock_llm_service
            assert service._vader_service is None

    def test_initialization_vader_only(self):
        """Test initialization with VADER only."""
        with patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            service = HybridSentimentService(
                use_llm=False,
                dual_model_strategy=False
            )
            
            assert service.use_llm is False
            assert service._vader_service == self.mock_vader_service
            assert service._llm_service is None

    def test_analyze_sentiment_dual_model_strong_llm(self):
        """Test dual model strategy with strong LLM signal."""
        with patch('app.services.hybrid_sentiment.get_llm_sentiment_service', return_value=self.mock_llm_service), \
             patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            
            service = HybridSentimentService(
                dual_model_strategy=True,
                strong_llm_threshold=0.2
            )
            
            # LLM returns strong positive signal
            self.mock_llm_service.analyze_sentiment.return_value = 0.8
            
            result = service.analyze_sentiment("I love this stock!")
            
            assert result == 0.8
            self.mock_llm_service.analyze_sentiment.assert_called_once_with("I love this stock!")
            # VADER should not be called since LLM signal is strong
            self.mock_vader_service.analyze_sentiment.assert_not_called()

    def test_analyze_sentiment_dual_model_weak_llm_strong_vader(self):
        """Test dual model strategy with weak LLM, strong VADER."""
        with patch('app.services.hybrid_sentiment.get_llm_sentiment_service', return_value=self.mock_llm_service), \
             patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            
            service = HybridSentimentService(
                dual_model_strategy=True,
                strong_llm_threshold=0.2
            )
            
            # LLM returns weak signal
            self.mock_llm_service.analyze_sentiment.return_value = 0.1
            # VADER returns stronger signal
            self.mock_vader_service.analyze_sentiment.return_value = 0.6
            
            result = service.analyze_sentiment("This stock is okay")
            
            assert result == 0.6  # Should use VADER since it's further from neutral
            self.mock_llm_service.analyze_sentiment.assert_called_once()
            self.mock_vader_service.analyze_sentiment.assert_called_once()

    def test_analyze_sentiment_dual_model_weak_llm_weak_vader(self):
        """Test dual model strategy with both weak signals."""
        with patch('app.services.hybrid_sentiment.get_llm_sentiment_service', return_value=self.mock_llm_service), \
             patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            
            service = HybridSentimentService(
                dual_model_strategy=True,
                strong_llm_threshold=0.2
            )
            
            # Both return weak signals
            self.mock_llm_service.analyze_sentiment.return_value = 0.1
            self.mock_vader_service.analyze_sentiment.return_value = 0.05
            
            result = service.analyze_sentiment("The stock price is $100")
            
            assert result == 0.1  # Should use LLM since it's slightly further from neutral
            self.mock_llm_service.analyze_sentiment.assert_called_once()
            self.mock_vader_service.analyze_sentiment.assert_called_once()

    def test_analyze_sentiment_llm_fallback_to_vader(self):
        """Test LLM fallback to VADER when LLM fails."""
        with patch('app.services.hybrid_sentiment.get_llm_sentiment_service', return_value=self.mock_llm_service), \
             patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            
            service = HybridSentimentService(
                use_llm=True,
                dual_model_strategy=False,
                fallback_to_vader=True
            )
            
            # LLM fails
            self.mock_llm_service.analyze_sentiment.side_effect = Exception("LLM Error")
            # VADER succeeds
            self.mock_vader_service.analyze_sentiment.return_value = 0.5
            
            result = service.analyze_sentiment("Test text")
            
            assert result == 0.5
            self.mock_llm_service.analyze_sentiment.assert_called_once()
            self.mock_vader_service.analyze_sentiment.assert_called_once()

    def test_analyze_sentiment_vader_only(self):
        """Test VADER-only sentiment analysis."""
        with patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            service = HybridSentimentService(use_llm=False)
            
            self.mock_vader_service.analyze_sentiment.return_value = 0.3
            
            result = service.analyze_sentiment("Test text")
            
            assert result == 0.3
            self.mock_vader_service.analyze_sentiment.assert_called_once_with("Test text")

    def test_analyze_sentiment_empty_text(self):
        """Test hybrid sentiment analysis with empty text."""
        with patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            service = HybridSentimentService(use_llm=False)
            
            with pytest.raises(ValueError, match="Text cannot be empty or None"):
                service.analyze_sentiment("")

    def test_analyze_sentiment_no_services_available(self):
        """Test error when no services are available."""
        service = HybridSentimentService(use_llm=False, dual_model_strategy=False)
        service._vader_service = None
        
        with pytest.raises(RuntimeError, match="No sentiment analysis service available"):
            service.analyze_sentiment("Test text")

    def test_get_sentiment_label(self):
        """Test sentiment label conversion."""
        with patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            service = HybridSentimentService(use_llm=False)
            
            assert service.get_sentiment_label(0.1) == "Positive"
            assert service.get_sentiment_label(-0.1) == "Negative"
            assert service.get_sentiment_label(0.05) == "Neutral"

    def test_analyze_with_label(self):
        """Test analyze_with_label method."""
        with patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            service = HybridSentimentService(use_llm=False)
            
            with patch.object(service, 'analyze_sentiment', return_value=0.7):
                score, label = service.analyze_with_label("Great stock!")
                
                assert score == 0.7
                assert label == "Positive"

    def test_get_service_info(self):
        """Test service information retrieval."""
        with patch('app.services.hybrid_sentiment.get_llm_sentiment_service', return_value=self.mock_llm_service):
            service = HybridSentimentService(
                use_llm=True,
                llm_model_name="test-model",
                use_gpu=True,
                fallback_to_vader=True
            )
            
            self.mock_llm_service.get_model_info.return_value = {"model_name": "test-model"}
            
            info = service.get_service_info()
            
            assert info["use_llm"] is True
            assert info["llm_model_name"] == "test-model"
            assert info["use_gpu"] is True
            assert info["fallback_to_vader"] is True


class TestSentimentAnalysisRealWorldExamples:
    """Test sentiment analysis with real-world Reddit examples."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_vader_service = Mock()
        self.mock_llm_service = Mock()

    def test_wallstreetbets_meme_sentiment(self):
        """Test sentiment analysis of WallStreetBets meme language."""
        with patch('app.services.hybrid_sentiment.get_llm_sentiment_service', return_value=self.mock_llm_service), \
             patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            
            service = HybridSentimentService(dual_model_strategy=True)
            
            # Mock LLM to return strong positive sentiment for meme language
            self.mock_llm_service.analyze_sentiment.return_value = 0.8
            
            text = "🚀 $GME to the moon! 💎🙌 Diamond hands! This is the way! HODL!"
            result = service.analyze_sentiment(text)
            
            assert result == 0.8
            self.mock_llm_service.analyze_sentiment.assert_called_once_with(text)

    def test_technical_analysis_sentiment(self):
        """Test sentiment analysis of technical analysis discussions."""
        with patch('app.services.hybrid_sentiment.get_llm_sentiment_service', return_value=self.mock_llm_service), \
             patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            
            service = HybridSentimentService(dual_model_strategy=True)
            
            # Mock LLM to return neutral sentiment for technical analysis
            self.mock_llm_service.analyze_sentiment.return_value = 0.1
            # Mock VADER to return slightly more positive sentiment
            self.mock_vader_service.analyze_sentiment.return_value = 0.2
            
            text = "Looking at the RSI and MACD indicators, $AAPL shows bullish divergence. Support at $150."
            result = service.analyze_sentiment(text)
            
            assert result == 0.2  # Should use VADER since it's further from neutral
            self.mock_llm_service.analyze_sentiment.assert_called_once()
            self.mock_vader_service.analyze_sentiment.assert_called_once()

    def test_earnings_discussion_sentiment(self):
        """Test sentiment analysis of earnings discussions."""
        with patch('app.services.hybrid_sentiment.get_llm_sentiment_service', return_value=self.mock_llm_service), \
             patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            
            service = HybridSentimentService(dual_model_strategy=True)
            
            # Mock LLM to return strong positive sentiment for good earnings
            self.mock_llm_service.analyze_sentiment.return_value = 0.9
            
            text = "Microsoft crushed earnings! Revenue up 20% YoY. $MSFT is a buy!"
            result = service.analyze_sentiment(text)
            
            assert result == 0.9
            self.mock_llm_service.analyze_sentiment.assert_called_once()

    def test_negative_sentiment_analysis(self):
        """Test negative sentiment analysis."""
        with patch('app.services.hybrid_sentiment.get_llm_sentiment_service', return_value=self.mock_llm_service), \
             patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            
            service = HybridSentimentService(dual_model_strategy=True)
            
            # Mock LLM to return strong negative sentiment
            self.mock_llm_service.analyze_sentiment.return_value = -0.8
            
            text = "This stock is a complete disaster! Lost 50% of my portfolio. $TSLA is overvalued!"
            result = service.analyze_sentiment(text)
            
            assert result == -0.8
            self.mock_llm_service.analyze_sentiment.assert_called_once()

    def test_mixed_sentiment_analysis(self):
        """Test mixed sentiment analysis."""
        with patch('app.services.hybrid_sentiment.get_llm_sentiment_service', return_value=self.mock_llm_service), \
             patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            
            service = HybridSentimentService(dual_model_strategy=True)
            
            # Mock LLM to return weak positive sentiment
            self.mock_llm_service.analyze_sentiment.return_value = 0.1
            # Mock VADER to return weak negative sentiment
            self.mock_vader_service.analyze_sentiment.return_value = -0.15
            
            text = "The stock has potential but the market is volatile. Not sure about $NVDA right now."
            result = service.analyze_sentiment(text)
            
            assert result == -0.15  # Should use VADER since it's further from neutral
            self.mock_llm_service.analyze_sentiment.assert_called_once()
            self.mock_vader_service.analyze_sentiment.assert_called_once()

    def test_sarcasm_detection(self):
        """Test sentiment analysis with sarcastic content."""
        with patch('app.services.hybrid_sentiment.get_llm_sentiment_service', return_value=self.mock_llm_service), \
             patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            
            service = HybridSentimentService(dual_model_strategy=True)
            
            # Mock LLM to detect sarcasm (negative sentiment)
            self.mock_llm_service.analyze_sentiment.return_value = -0.6
            # Mock VADER to miss sarcasm (positive sentiment)
            self.mock_vader_service.analyze_sentiment.return_value = 0.3
            
            text = "Oh great, another 20% drop. Thanks $GME, you're really helping my portfolio!"
            result = service.analyze_sentiment(text)
            
            assert result == -0.6  # Should use LLM since it's further from neutral
            self.mock_llm_service.analyze_sentiment.assert_called_once()
            self.mock_vader_service.analyze_sentiment.assert_called_once()

    def test_financial_terminology_sentiment(self):
        """Test sentiment analysis with financial terminology."""
        with patch('app.services.hybrid_sentiment.get_llm_sentiment_service', return_value=self.mock_llm_service), \
             patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            
            service = HybridSentimentService(dual_model_strategy=True)
            
            # Mock LLM to understand financial context better
            self.mock_llm_service.analyze_sentiment.return_value = 0.7
            
            text = "Strong fundamentals, solid balance sheet, and excellent cash flow. $AAPL is undervalued."
            result = service.analyze_sentiment(text)
            
            assert result == 0.7
            self.mock_llm_service.analyze_sentiment.assert_called_once()

    def test_emoji_heavy_sentiment(self):
        """Test sentiment analysis with heavy emoji usage."""
        with patch('app.services.hybrid_sentiment.get_llm_sentiment_service', return_value=self.mock_llm_service), \
             patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            
            service = HybridSentimentService(dual_model_strategy=True)
            
            # Mock LLM to handle emojis well
            self.mock_llm_service.analyze_sentiment.return_value = 0.8
            
            text = "🚀🚀🚀 $TSLA 🚀🚀🚀 TO THE MOON! 🌙💎🙌 DIAMOND HANDS! 🚀🚀🚀"
            result = service.analyze_sentiment(text)
            
            assert result == 0.8
            self.mock_llm_service.analyze_sentiment.assert_called_once()

    def test_long_form_analysis_sentiment(self):
        """Test sentiment analysis of long-form analysis posts."""
        with patch('app.services.hybrid_sentiment.get_llm_sentiment_service', return_value=self.mock_llm_service), \
             patch('app.services.hybrid_sentiment.get_vader_service', return_value=self.mock_vader_service):
            
            service = HybridSentimentService(dual_model_strategy=True)
            
            # Mock LLM to return moderate positive sentiment for balanced analysis
            self.mock_llm_service.analyze_sentiment.return_value = 0.4
            
            text = """
            After analyzing the Q4 earnings and market conditions, I believe $AAPL has strong long-term potential.
            The iPhone sales were solid, services revenue is growing, and the company has a strong balance sheet.
            However, there are concerns about China exposure and valuation. Overall, I'm cautiously optimistic.
            """
            result = service.analyze_sentiment(text)
            
            assert result == 0.4
            self.mock_llm_service.analyze_sentiment.assert_called_once()
