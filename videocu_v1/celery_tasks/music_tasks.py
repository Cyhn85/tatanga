"""
VIDEOCU v1 - Music Celery Tasks
Async music composition tasks using Celery

Tasks:
- extract_melody: Extract melody from audio using Basic Pitch
- extract_rhythm: Extract rhythm patterns using librosa
- compose_final: Combine all layers into final composition
- add_ai_arrangement: Add AI-generated arrangement (GPU required)
- run_colab_gpu_task: Run GPU-intensive tasks on Google Colab
- auto_detect_and_process: Auto-detect audio type and process accordingly
"""

import logging
import os
from typing import Dict, List, Optional
from celery import shared_task, chain, group

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='music.extract_melody', queue='music')
def extract_melody(self, project_id: str, input_id: str) -> Dict:
    """
    Extract melody from audio input using Basic Pitch

    Args:
        project_id: Music project ID
        input_id: Audio input ID

    Returns:
        Result dict with midi_path
    """
    logger.info(f"[Celery] Extracting melody for input {input_id}")

    try:
        from modules.agent_memory import AgentMemory
        from modules.agents.composer_agent import ComposerAgent

        memory = AgentMemory()
        composer = ComposerAgent(memory=memory)

        # Get input info
        inputs = memory.get_project_inputs(project_id)
        target_input = next((i for i in inputs if i['input_id'] == input_id), None)

        if not target_input:
            return {'success': False, 'error': f'Input {input_id} not found'}

        audio_path = target_input.get('audio_path')
        if not audio_path:
            return {'success': False, 'error': 'No audio path'}

        # Process the audio
        result = composer.process_audio_input(
            project_id=project_id,
            audio_path=audio_path,
            input_type='melody'
        )

        memory.close()
        return result

    except Exception as e:
        logger.error(f"[Celery] Melody extraction failed: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(bind=True, name='music.extract_rhythm', queue='music')
def extract_rhythm(self, project_id: str, input_id: str) -> Dict:
    """
    Extract rhythm patterns from audio input

    Args:
        project_id: Music project ID
        input_id: Audio input ID

    Returns:
        Result dict with rhythm analysis
    """
    logger.info(f"[Celery] Extracting rhythm for input {input_id}")

    try:
        from modules.agent_memory import AgentMemory
        from modules.agents.composer_agent import ComposerAgent

        memory = AgentMemory()
        composer = ComposerAgent(memory=memory)

        # Get input info
        inputs = memory.get_project_inputs(project_id)
        target_input = next((i for i in inputs if i['input_id'] == input_id), None)

        if not target_input:
            return {'success': False, 'error': f'Input {input_id} not found'}

        audio_path = target_input.get('audio_path')
        if not audio_path:
            return {'success': False, 'error': 'No audio path'}

        # Process as rhythm
        result = composer.process_audio_input(
            project_id=project_id,
            audio_path=audio_path,
            input_type='rhythm'
        )

        memory.close()
        return result

    except Exception as e:
        logger.error(f"[Celery] Rhythm extraction failed: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(bind=True, name='music.compose_final', queue='music')
def compose_final(self, project_id: str, extraction_results: List[Dict] = None) -> Dict:
    """
    Compose final audio from all project inputs

    Args:
        project_id: Music project ID
        extraction_results: Results from previous extraction tasks (optional)

    Returns:
        Result dict with final audio path
    """
    logger.info(f"[Celery] Composing final for project {project_id}")

    try:
        from modules.agent_memory import AgentMemory
        from modules.agents.composer_agent import ComposerAgent

        memory = AgentMemory()
        composer = ComposerAgent(memory=memory)

        result = composer.compose_project(project_id)

        memory.close()
        return result

    except Exception as e:
        logger.error(f"[Celery] Final composition failed: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(bind=True, name='music.add_ai_arrangement', queue='music')
def add_ai_arrangement(self, project_id: str, style: str = None) -> Dict:
    """
    Add AI-generated arrangement to project (requires GPU)

    Args:
        project_id: Music project ID
        style: Music style override

    Returns:
        Result dict with AI arrangement path
    """
    logger.info(f"[Celery] Adding AI arrangement to project {project_id}")

    try:
        from modules.agent_memory import AgentMemory
        from modules.agents.composer_agent import ComposerAgent

        memory = AgentMemory()
        composer = ComposerAgent(memory=memory)

        result = composer.add_ai_arrangement(project_id, style)

        memory.close()
        return result

    except Exception as e:
        logger.error(f"[Celery] AI arrangement failed: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(bind=True, name='music.process_voice_input', queue='music')
def process_voice_input(self, user_id: str, audio_path: str, project_name: str = None,
                        style: str = 'pop', input_type: str = 'melody') -> Dict:
    """
    Process a voice input and optionally create a new project

    Args:
        user_id: Telegram user ID
        audio_path: Path to downloaded audio file
        project_name: Name for new project (if creating)
        style: Music style
        input_type: Type of input (melody, rhythm, sample)

    Returns:
        Result dict with project and input info
    """
    logger.info(f"[Celery] Processing voice input for user {user_id}")

    try:
        from modules.agent_memory import AgentMemory
        from modules.agents.composer_agent import ComposerAgent

        memory = AgentMemory()
        composer = ComposerAgent(memory=memory)

        # Check for active project or create new
        project = composer.get_active_project(user_id)

        if not project and project_name:
            project = composer.create_project(user_id, project_name, style)

        if not project:
            memory.close()
            return {'success': False, 'error': 'No project available'}

        # Process the audio
        result = composer.process_audio_input(
            project_id=project['project_id'],
            audio_path=audio_path,
            input_type=input_type
        )

        result['project'] = project
        memory.close()
        return result

    except Exception as e:
        logger.error(f"[Celery] Voice input processing failed: {e}")
        return {'success': False, 'error': str(e)}


def full_composition_chain(project_id: str, input_ids: List[str] = None) -> chain:
    """
    Create a full composition chain for a project

    Args:
        project_id: Music project ID
        input_ids: List of input IDs to process (if None, processes all)

    Returns:
        Celery chain ready to execute
    """
    from celery import chain, group

    # If specific inputs provided, extract them first
    if input_ids:
        extraction_jobs = group([
            extract_melody.s(project_id, iid)
            for iid in input_ids
        ])

        return chain(
            extraction_jobs,
            compose_final.s(project_id)
        )
    else:
        # Just compose with existing processed inputs
        return compose_final.s(project_id)


def full_composition_with_ai(project_id: str, style: str = 'pop') -> chain:
    """
    Create composition chain with AI arrangement

    Args:
        project_id: Music project ID
        style: Music style for AI arrangement

    Returns:
        Celery chain ready to execute
    """
    from celery import chain

    return chain(
        compose_final.s(project_id),
        add_ai_arrangement.s(project_id, style)
    )


# Task status helpers
def get_task_status(task_id: str) -> Dict:
    """Get status of a music task"""
    from celery.result import AsyncResult

    result = AsyncResult(task_id)

    return {
        'task_id': task_id,
        'status': result.status,
        'ready': result.ready(),
        'successful': result.successful() if result.ready() else None,
        'result': result.result if result.ready() else None
    }


# ========== Beatbox Transformation Tasks ==========

@shared_task(bind=True, name='music.transform_beatbox', queue='music')
def transform_beatbox(self, project_id: str, audio_path: str,
                      kit: str = '808', start_time: float = 0.0) -> Dict:
    """
    Transform beatbox audio to professional drum sounds

    Args:
        project_id: Music project ID
        audio_path: Path to beatbox audio file
        kit: Sample kit to use (808, 909, acoustic, electronic)
        start_time: Start time in composition

    Returns:
        Result dict with transformed audio path and detected sounds
    """
    logger.info(f"[Celery] Transforming beatbox with {kit} kit for project {project_id}")

    try:
        from modules.agent_memory import AgentMemory
        from modules.agents.composer_agent import ComposerAgent

        memory = AgentMemory()
        composer = ComposerAgent(memory=memory)

        result = composer.process_beatbox_input(
            project_id=project_id,
            audio_path=audio_path,
            kit=kit,
            start_time=start_time
        )

        memory.close()
        return result

    except Exception as e:
        logger.error(f"[Celery] Beatbox transformation failed: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(bind=True, name='music.add_raw_voice', queue='music')
def add_raw_voice(self, project_id: str, audio_path: str,
                  start_time: float = 0.0, effect: str = 'none',
                  label: str = None) -> Dict:
    """
    Add raw voice to project with optional effects

    Args:
        project_id: Music project ID
        audio_path: Path to voice audio file
        start_time: Start time in composition
        effect: Effect to apply (none, reverb, delay, autotune)
        label: Label for this voice layer

    Returns:
        Result dict with processed audio path
    """
    logger.info(f"[Celery] Adding raw voice to project {project_id} with {effect} effect")

    try:
        from modules.agent_memory import AgentMemory
        from modules.agents.composer_agent import ComposerAgent

        memory = AgentMemory()
        composer = ComposerAgent(memory=memory)

        result = composer.add_raw_voice(
            project_id=project_id,
            audio_path=audio_path,
            start_time=start_time,
            effect=effect,
            label=label
        )

        memory.close()
        return result

    except Exception as e:
        logger.error(f"[Celery] Raw voice processing failed: {e}")
        return {'success': False, 'error': str(e)}


def beatbox_composition_chain(project_id: str, beatbox_audio: str,
                              kit: str = '808', melody_audio: str = None) -> chain:
    """
    Create a composition chain that includes beatbox transformation

    Args:
        project_id: Music project ID
        beatbox_audio: Path to beatbox audio
        kit: Sample kit for beatbox
        melody_audio: Optional melody audio to include

    Returns:
        Celery chain ready to execute
    """
    from celery import chain, group

    tasks = []

    # Transform beatbox
    tasks.append(transform_beatbox.s(project_id, beatbox_audio, kit))

    # If melody provided, extract it in parallel
    if melody_audio:
        tasks = [group([
            transform_beatbox.s(project_id, beatbox_audio, kit),
            extract_melody.s(project_id, melody_audio)
        ])]

    # Final composition
    tasks.append(compose_final.s(project_id))

    return chain(*tasks)


# ========== Colab GPU Tasks ==========

@shared_task(bind=True, name='music.run_colab_gpu', queue='music')
def run_colab_gpu_task(self, operation: str, params: Dict) -> Dict:
    """
    Run GPU-intensive AI operations on Google Colab via Gradio API.

    Args:
        operation: Operation type - 'extract_melody' | 'generate_music' |
                   'transform_melody' | 'separate_stems'
        params: Operation parameters:
            - audio_path: str (for extract/transform/separate)
            - prompt: str (for generate)
            - duration: int (for generate/transform, default 30)
            - style: str (for transform)

    Returns:
        Dict with success status and result or error

    Example:
        run_colab_gpu_task.delay('extract_melody', {'audio_path': '/path/to/audio.wav'})
        run_colab_gpu_task.delay('generate_music', {'prompt': 'hip hop beat', 'duration': 30})
    """
    logger.info(f"[Celery] Running Colab GPU task: {operation}")

    try:
        from modules.colab import ColabBridge

        bridge = ColabBridge()

        # Check Colab availability
        if not bridge.is_available():
            logger.warning("[Celery] Colab GPU unavailable, will use fallback if possible")
            return {
                'success': False,
                'error': 'Colab GPU unavailable. Start Colab notebook and run launch_gradio()',
                'fallback': True
            }

        # Update task state
        self.update_state(state='PROCESSING', meta={
            'operation': operation,
            'progress': 10
        })

        result = None

        if operation == 'extract_melody':
            audio_path = params.get('audio_path')
            if not audio_path:
                return {'success': False, 'error': 'audio_path required for extract_melody'}

            self.update_state(state='PROCESSING', meta={'operation': operation, 'progress': 30})
            result = bridge.extract_melody(audio_path)

        elif operation == 'generate_music':
            prompt = params.get('prompt', 'upbeat electronic music')
            duration = params.get('duration', 30)

            self.update_state(state='PROCESSING', meta={'operation': operation, 'progress': 30})
            result = bridge.generate_music(prompt=prompt, duration=duration)

        elif operation == 'transform_melody':
            audio_path = params.get('audio_path')
            if not audio_path:
                return {'success': False, 'error': 'audio_path required for transform_melody'}

            style = params.get('style', 'professional pop with synth and bass')
            duration = params.get('duration', 30)

            self.update_state(state='PROCESSING', meta={'operation': operation, 'progress': 30})
            result = bridge.transform_melody(
                audio_path=audio_path,
                style_prompt=style,
                duration=duration
            )

        elif operation == 'separate_stems':
            audio_path = params.get('audio_path')
            if not audio_path:
                return {'success': False, 'error': 'audio_path required for separate_stems'}

            self.update_state(state='PROCESSING', meta={'operation': operation, 'progress': 30})
            result = bridge.separate_stems(audio_path)

        else:
            return {'success': False, 'error': f'Unknown operation: {operation}'}

        self.update_state(state='PROCESSING', meta={'operation': operation, 'progress': 90})

        logger.info(f"[Celery] Colab GPU task completed: {operation}")
        return {'success': True, 'operation': operation, 'result': result}

    except Exception as e:
        logger.error(f"[Celery] Colab GPU task failed: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(bind=True, name='music.auto_detect_and_process', queue='music')
def auto_detect_and_process(self, project_id: str, audio_path: str,
                            user_id: str = None) -> Dict:
    """
    Automatically detect audio type and process accordingly.

    Detection logic:
    - High zero-crossing rate + low spectral centroid → Beatbox → transform to 808/909
    - High spectral centroid → Humming/Melody → extract MIDI via Basic Pitch
    - Mid-range values → Full song → separate stems (vocals + instrumental)

    Args:
        project_id: Music project ID
        audio_path: Path to audio file
        user_id: Optional user ID for notifications

    Returns:
        Dict with detected_type, operation, and task_id
    """
    logger.info(f"[Celery] Auto-detecting audio type for project {project_id}")

    try:
        import librosa
        import numpy as np

        # Load and analyze audio
        y, sr = librosa.load(audio_path, sr=22050, duration=30)  # Analyze first 30s

        # Extract features
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr).mean()
        zero_crossing_rate = librosa.feature.zero_crossing_rate(y).mean()
        rms_energy = librosa.feature.rms(y=y).mean()

        # Log analysis
        logger.info(f"[Celery] Audio analysis - ZCR: {zero_crossing_rate:.4f}, "
                   f"Centroid: {spectral_centroid:.1f}, Tempo: {tempo:.1f}, RMS: {rms_energy:.4f}")

        # Decision logic
        detected_type = None
        operation = None
        params = {'audio_path': audio_path}

        if zero_crossing_rate > 0.12 and spectral_centroid < 2500:
            # Beatbox-like: high zero-crossing, low spectral centroid (percussive sounds)
            detected_type = 'beatbox'
            operation = 'transform_beatbox'
            params['kit'] = '808'

            # Use local beatbox transform (doesn't need GPU)
            result = transform_beatbox.delay(project_id, audio_path, '808')
            task_id = result.id

        elif spectral_centroid > 2500 or (rms_energy < 0.1 and spectral_centroid > 1500):
            # Melody/Humming: high spectral centroid or quiet + melodic
            detected_type = 'melody'
            operation = 'extract_melody'

            # Use Colab GPU for Basic Pitch
            result = run_colab_gpu_task.delay('extract_melody', params)
            task_id = result.id

        else:
            # Full song: mixed characteristics
            detected_type = 'song'
            operation = 'separate_stems'

            # Use Colab GPU for Demucs
            result = run_colab_gpu_task.delay('separate_stems', params)
            task_id = result.id

        logger.info(f"[Celery] Detected type: {detected_type}, operation: {operation}")

        return {
            'success': True,
            'detected_type': detected_type,
            'operation': operation,
            'task_id': task_id,
            'analysis': {
                'zero_crossing_rate': float(zero_crossing_rate),
                'spectral_centroid': float(spectral_centroid),
                'tempo': float(tempo),
                'rms_energy': float(rms_energy)
            }
        }

    except Exception as e:
        logger.error(f"[Celery] Auto-detection failed: {e}")
        return {'success': False, 'error': str(e)}


# ========== Colab Task Chains ==========

def colab_melody_to_music_chain(audio_path: str, style: str = 'pop',
                                 duration: int = 30) -> chain:
    """
    Chain: Extract melody from humming → Transform to professional music

    Args:
        audio_path: Path to humming/melody audio
        style: Music style for transformation
        duration: Duration of output

    Returns:
        Celery chain ready to execute
    """
    return chain(
        run_colab_gpu_task.s('extract_melody', {'audio_path': audio_path}),
        run_colab_gpu_task.s('transform_melody', {
            'audio_path': audio_path,  # Will be replaced with extracted melody
            'style': style,
            'duration': duration
        })
    )


def colab_full_production_chain(audio_path: str, style: str = 'pop') -> chain:
    """
    Full production chain: Separate stems → Generate backing track → Combine

    Args:
        audio_path: Path to input audio (song with vocals)
        style: Style for AI-generated backing

    Returns:
        Celery chain ready to execute
    """
    return chain(
        run_colab_gpu_task.s('separate_stems', {'audio_path': audio_path}),
        run_colab_gpu_task.s('generate_music', {
            'prompt': f'{style} instrumental backing track',
            'duration': 30
        })
    )
