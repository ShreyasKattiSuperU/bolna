import base64
import json
import os
import audioop
import uuid
import traceback
from dotenv import load_dotenv
from .default import DefaultOutputHandler
from bolna.helpers.logger_config import configure_logger
logger = configure_logger(__name__)
load_dotenv()


class TelephonyOutputHandler(DefaultOutputHandler):
    def __init__(self, io_provider, websocket=None, mark_event_meta_data=None, log_dir_name=None):
        super().__init__(io_provider, websocket, log_dir_name)
        self.mark_event_meta_data = mark_event_meta_data

        self.stream_sid = None
        self.current_request_id = None
        self.rejected_request_ids = set()

    async def handle_interruption(self):
        pass

    async def form_media_message(self, audio_data, audio_format):
        pass

    async def form_mark_message(self, mark_id):
        pass

    async def handle(self, ws_data_packet):
        try:
            audio_chunk = ws_data_packet.get('data')
            meta_info = ws_data_packet.get('meta_info')
            if self.stream_sid is None:
                self.stream_sid = meta_info.get('stream_sid', None)

            logger.info(f"Sending Message {self.current_request_id} and {self.stream_sid} and {meta_info}")
            # TODO revisit this - need to change this logic
            if meta_info.get('message_category', '') == 'agent_hangup' and meta_info.get('is_final_chunk_of_entire_response', True):
                self.is_last_hangup_chunk_sent = True

            # if meta_info.get('message_category', '') == 'agent_welcome_message' and meta_info.get('is_final_chunk_of_entire_response', True):
            #     self.is_welcome_message_sent = True

            try:
                # TODO check with Prateek about this
                # if self.current_request_id == meta_info['request_id']:
                #     if len(audio_chunk) == 1:
                #         audio_chunk += b'\x00'

                if len(audio_chunk) == 1:
                    audio_chunk += b'\x00'

                if audio_chunk and self.stream_sid and len(audio_chunk) != 1:
                    audio_format = meta_info.get("format", "wav")
                    logger.info(f"Sending message {len(audio_chunk)} {audio_format}")

                    if audio_format == 'pcm' and meta_info.get('message_category', '') == 'agent_welcome_message' and self.io_provider == 'plivo' and meta_info['cached'] is True:
                        audio_format = 'wav'
                    media_message = await self.form_media_message(audio_chunk, audio_format)
                    await self.websocket.send_text(json.dumps(media_message))
                    logger.info(f"Meta info received - {meta_info}")

                    # TODO when meta_info is -1 we could maybe get text_syn from text
                    if meta_info["sequence_id"] == -1 and not meta_info.get("text_synthesized", ""):
                        text_synthesized = meta_info.get("text", "")
                    else:
                        text_synthesized = meta_info.get("text_synthesized", "")

                    mark_event_meta_data = {
                        "text_synthesized": text_synthesized,
                        "type": meta_info.get('message_category', ''),
                        "is_first_chunk": meta_info.get("is_first_chunk", False),
                        "is_final_chunk": True if (meta_info["sequence_id"] == -1 or (meta_info.get("end_of_llm_stream", False) and meta_info.get("end_of_synthesizer_stream", False))) else False
                    }
                    mark_id = meta_info.get("mark_id") if (meta_info.get("mark_id") and meta_info.get("mark_id") != "") else str(uuid.uuid4())
                    logger.info(f"Mark meta data being saved for mark id - {mark_id} is - {mark_event_meta_data}")
                    self.mark_event_meta_data.update_data(mark_id, mark_event_meta_data)
                    mark_message = await self.form_mark_message(mark_id)
                    logger.info(f"Sending mark event - {mark_message}")
                    await self.websocket.send_text(json.dumps(mark_message))

                    # if meta_info.get('message_category', '') == 'agent_welcome_message' and meta_info.get(
                    #         'is_final_chunk_of_entire_response', True):
                    #     # mark_id = str(uuid.uuid4())
                    #     mark_event_type = "agent_welcome_message"

                else:
                    logger.info("Not sending")
            except Exception as e:
                traceback.print_exc()
                logger.info(f'something went wrong while sending message to twilio {e}')

        except Exception as e:
            logger.info(f'something went wrong while handling twilio {e}')
