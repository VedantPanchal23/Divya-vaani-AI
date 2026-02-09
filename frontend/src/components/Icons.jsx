/**
 * Icons — React Icons + Custom Spiritual SVGs
 */

import {
    FiUpload, FiSun, FiMoon, FiTrash2, FiRefreshCw, FiPlay, FiPause, FiSquare,
    FiVolume2, FiVolumeX, FiLoader, FiAlertCircle, FiCheckCircle, FiClock,
    FiChevronDown, FiChevronUp, FiChevronLeft, FiSend, FiX, FiSettings, FiInfo,
    FiSearch, FiArrowLeft, FiFileText, FiMessageCircle, FiBook, FiBookOpen,
    FiList, FiMic, FiVideo, FiMusic, FiGlobe,
    FiMoreVertical, FiHelpCircle
} from 'react-icons/fi';

import {
    HiOutlineSparkles, HiOutlineLightBulb, HiOutlineTranslate,
    HiOutlineDocumentText
} from 'react-icons/hi';

/* Custom OM (ॐ) symbol — a proper spiritual identity */
const OmIcon = ({ size = 24, ...props }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
        <text x="50%" y="54%" dominantBaseline="middle" textAnchor="middle"
              fontSize="18" fontWeight="700" fill="currentColor"
              fontFamily="'Noto Sans Devanagari', serif">ॐ</text>
    </svg>
);

export const Icons = {
    // Brand
    Logo: OmIcon,
    Spiritual: OmIcon,

    // Theme
    Sun: (props) => <FiSun {...props} />,
    Moon: (props) => <FiMoon {...props} />,

    // Actions
    Upload: (props) => <FiUpload {...props} />,
    Send: (props) => <FiSend {...props} />,
    Delete: (props) => <FiTrash2 {...props} />,
    Refresh: (props) => <FiRefreshCw {...props} />,
    Close: (props) => <FiX {...props} />,
    Settings: (props) => <FiSettings {...props} />,
    Info: (props) => <FiInfo {...props} />,
    MoreVertical: (props) => <FiMoreVertical {...props} />,
    Search: (props) => <FiSearch {...props} />,
    Back: (props) => <FiArrowLeft {...props} />,

    // Media
    Play: (props) => <FiPlay {...props} />,
    Pause: (props) => <FiPause {...props} />,
    Stop: (props) => <FiSquare {...props} />,
    VolumeOn: (props) => <FiVolume2 {...props} />,
    VolumeOff: (props) => <FiVolumeX {...props} />,
    Mic: (props) => <FiMic {...props} />,
    Video: (props) => <FiVideo {...props} />,
    Music: (props) => <FiMusic {...props} />,

    // Status
    Loading: (props) => <FiLoader {...props} />,
    Error: (props) => <FiAlertCircle {...props} />,
    Success: (props) => <FiCheckCircle {...props} />,
    Clock: (props) => <FiClock {...props} />,

    // Content
    Transcript: (props) => <FiFileText {...props} />,
    Summary: (props) => <HiOutlineDocumentText {...props} />,
    Explanation: (props) => <HiOutlineLightBulb {...props} />,
    Chat: (props) => <FiMessageCircle {...props} />,
    Question: (props) => <FiHelpCircle {...props} />,
    Book: (props) => <FiBook {...props} />,
    BookOpen: (props) => <FiBookOpen {...props} />,
    List: (props) => <FiList {...props} />,
    Sessions: (props) => <FiBook {...props} />,

    // Features
    Sparkles: (props) => <HiOutlineSparkles {...props} />,
    Translate: (props) => <HiOutlineTranslate {...props} />,
    Speak: (props) => <FiVolume2 {...props} />,
    AI: (props) => <HiOutlineSparkles {...props} />,
    Globe: (props) => <FiGlobe {...props} />,

    // Chevrons
    ChevronDown: (props) => <FiChevronDown {...props} />,
    ChevronUp: (props) => <FiChevronUp {...props} />,
    ChevronLeft: (props) => <FiChevronLeft {...props} />,

    // Processing
    Processing: (props) => <FiLoader {...props} />,
    Done: (props) => <FiCheckCircle {...props} />,
    Pending: (props) => <FiClock {...props} />,
};

export default Icons;
